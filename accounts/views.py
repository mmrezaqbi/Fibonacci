from django.shortcuts import render , redirect
from django.contrib.auth import authenticate , login , logout
from django.contrib import messages
# Create your views here.



def login_user (request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']


        user = authenticate(request , username=username , password=password)
        if user is not None:
            login(request , user)
            messages.success(request , 'شما با موفقیت وارد شدید !')
            return redirect('application:home')
        
        else:
            messages.success(request , 'نام کاربری و یا رمز عبور اشتباه است !')
            return redirect('accounts:login')
        
    else:
        return render(request , 'base.html')


def logout_user(request):
    logout(request)
    messages.success(request , 'شما از حساب کاربری خود خارج شدید!')
    return redirect('accounts:login')