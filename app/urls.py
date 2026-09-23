from django.urls import path,include
from . import views


urlpatterns = [
        path('', views.index,name='home'),
        path('about/',views.about, name="about"),
        path('contact/',views.contact,name="contact"),

        #user login
        path('user_login/', views.user_login,name='user_login'),
        path('user_registration/', views.user_registration,name='user_registration'),
        path('user_logout/', views.user_logout, name='logout'),

        # otp login
        path('otp_login_home/',views.otp_login_home,name="otp_login_home"),
        path('otp_login_home/verify_otp/', views.verify_otp, name="verify_otp"),
        path('otp_login_home/verify_otp/resend_OTP/',views.resend_otp, name="resend_OTP"),


        # after user login
        path('user_home/', views.userhome, name='user_home'),
        path('user_contact/', views.user_contact, name='user_contact'),
        path('user_about/', views.user_about, name='user_about'),
        path('detect/',views.detect, name='detect'),
        path('result/<int:pk>/', views.result, name='result'),
        path('api/sample-analysis/', views.sample_analysis, name='sample_analysis'),
        path('history/',views.history, name='history'),
   
        #admin login
        path('admin_login/', views.admin_login,name='admin_login'),
        path('admin_registration/', views.admin_registration,name='admin_registration'),
        path('admin_logout/', views.admin_logout,name='admin_logout'),
        path('admin_home/', views.admin_home,name='admin_home'),
        path('view_user/', views.view_user,name='view_user'),
        path('view_contact/', views.view_contact,name='view_contact'),

        path('news_history/', views.news_history, name='news_history'),
        path('view_stat/',views.view_statistics, name='view_statistics'),
        path('delete-user/<int:user_id>/', views.delete_user, name='delete-user'),
        path('ban-user/<int:user_id>/', views.ban_user, name="ban-user"),
        path('unban-user/<int:user_id>/', views.unban_user, name="unban-user")

]