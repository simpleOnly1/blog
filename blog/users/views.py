import re

from django.db import DatabaseError
from django.shortcuts import render, redirect
from django.http.response import HttpResponseBadRequest

# Create your views here.
from django.urls import reverse

from django.views import View

#注册视图
from users.models import User


class RegisterView(View):

    def get(self,request):

        return render(request,'register.html')

    def post(self,request):
        """
        1.接收数据
        2.验证数据
            2.1 参数是否齐全
            2.2 手机号的格式是否正确
            2.3 密码是否符合格式
            2.4 密码和确认密码要一致
            2.5 短信验证码是否和redis中的一致
        3.保存注册信息
        4.返回响应跳转到指定页面
        :param request:
        :return:
        """
        # 1.接收数据
        mobile=request.POST.get('mobile')
        password=request.POST.get('password')
        password2=request.POST.get('password2')
        smscode=request.POST.get('sms_code')
        # 2.验证数据
        #     2.1 参数是否齐全
        if not all([mobile,password,password2,smscode]):
            return HttpResponseBadRequest('缺少必要的参数')
        #     2.2 手机号的格式是否正确
        if not re.match(r'^1[3-9]\d{9}$',mobile):
            return HttpResponseBadRequest('手机号不符合规则')
        #     2.3 密码是否符合格式
        if not re.match(r'^[0-9A-Za-z]{8,20}$',password):
            return HttpResponseBadRequest('请输入8-20位密码，密码是数字，字母')
        #     2.4 密码和确认密码要一致
        if password != password2:
            return HttpResponseBadRequest('两次密码不一致')
        #     2.5 短信验证码是否和redis中的一致
        redis_conn = get_redis_connection('default')
        redis_sms_code=redis_conn.get('sms:%s'%mobile)
        if redis_sms_code is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != redis_sms_code.decode():
            return HttpResponseBadRequest('短信验证码不一致')
        # 3.保存注册信息
        # create_user 可以使用系统的方法来对密码进行加密
        try:
            user=User.objects.create_user(username=mobile,
                                      mobile=mobile,
                                      password=password)
        except DatabaseError as e:
            logger.error(e)
            return HttpResponseBadRequest('注册失败')
        from django.contrib.auth import login
        login(request,user)
        #4.返回响应跳转的到指定页面
        #暂时返回一个注册成功的信息，后续在实现跳转到指定页面

        #redirect 是进行重定向
        #reverse 是可以通过namespace:name来获取到视图所对应的路由
        response = redirect(reverse('home:index'))
        #return HttpResponse('注册成功，重定向到首页')

        #设置cookie信息，以方便首页中用户信息的判断和用户信息的展示
        response.set_cookies('is_login',True)
        response.set_cookies('username',user.username,max_age=7*24*3600)

        return response

from django.http.response import HttpResponseBadRequest
from libs.captcha.captcha import captcha
from django_redis import get_redis_connection
from django.http import HttpResponse

class ImageCodeView(View):

    def get(self,request):
        """
        1.接收前段传递过来的uuid
        2.判断uuid是否获取到
        3.通过调用captcha来生成图片验证码（图片二进制和图片内容）
        4.将图片的内容保存在redis
            uuid作为key，图片中的内容作为一个value同时我们还需要设置一个实效
        5.返回图片的二进制
        :param request:
        :return:
        """
        # 1.接收前段传递过来的uuid
        uuid = request.GET.get('uuid')
        # 2.判断uuid是否获取到
        if uuid is None:
            return HttpResponseBadRequest('没有传递uuid')
        # 3.通过调用captcha来生成图片验证码（图片二进制和图片内容）
        text, image = captcha.generate_captcha()
        # 4.将图片的内容保存在redis
        #     uuid作为key，图片中的内容作为一个value同时我们还需要设置一个实效
        redis_conn = get_redis_connection('default')
        # key: 设置为uuid
        # seconds: 过期秒数 300秒 5分钟的过期时间
        # #value: text
        redis_conn.setex('img:%s'%uuid,300,text)
        # 5.返回图片的二进制
        return HttpResponse(image,content_type='image/jpeg')

from django.http.response import JsonResponse
from utils.response_code import RETCODE
import logging
from random import randint
from libs.yuntongxun.sms import CCP
logger = logging.getLogger('django')
class SmsCodeView(View):
    def get(self,request):
        """
        1.接收参数（查询字符串的形式传递过来）
        2.参数的验证
            2.1 验证参数是否齐全
            2.2 图片验证码的验证
                连接redis,获取redis中的图片就可以删除图片
                判断图片验证码是否存在
                如果图片验证码未过期，我们获取到之后就可以删除图片
                比对图片验证码
        3.生成短信验证码
        4.保存短信验证码到redis中
        5.发送短信
        6.返回响应
        :param request:
        :return:
        """
        # 1.接收参数（查询字符串的形式传递过来）
        mobile = request.GET.get('mobile')
        image_code = request.GET.get('image_code')
        uuid = request.GET.get('uuid')
        # 2.参数的验证
        #     2.1 验证参数是否齐全
        if not all([mobile,image_code,uuid]):
            return JsonResponse({'code':RETCODE.NECESSARYPARAMERR,'errmsg':'缺少必要的参数'})
        #     2.2 图片验证码的验证
        #         连接redis, 获取redis中的图片就可以删除图片
        redis_conn = get_redis_connection('default')
        redis_image_code = redis_conn.get('img:%s'%uuid)
        #         判断图片验证码是否存在
        if redis_image_code is None:
            return JsonResponse({'code':RETCODE.IMAGECODEERR,'errmsg':'图片验证码已过期'})
        #         如果图片验证码未过期，我们获取到之后就可以删除图片
        try:
            redis_conn.delete('img:%s'%uuid)
        except Exception as e:
            logger.error(e)
        #         比对图片验证码,注意大小写问题，redis的数据是byte类型
        if redis_image_code.decode().lower()!=image_code.lower():
            return JsonResponse({'code':RETCODE.IMAGECODEERR,'errmsg':'图片验证码错误'})
        # 3.生成短信验证码
        sms_code = '%06d'%randint(0,999999)
        #为了后续比对方便，可以将短信验证码记录到日志中
        logger.info(sms_code)
        # 4.保存短信验证码到redis中
        redis_conn.setex('sms:%s'%mobile,300,sms_code)
        # 5.发送短信
        # 注意： 测试的短信模板编号为1
        # 参数1： 测试手机号
        # 参数2：模板内容列表： {1} 短信验证码   {2} 分钟有效
        # 参数3：模板 免费开发测试使用的模板ID为1
        CCP().send_template_sms('mobile', [sms_code, 5], 1)
        # 6.返回响应
        return JsonResponse({'code':RETCODE.OK,'errmsg':'短信发送成功'})