[app]
title = My AI
package.name = myai
package.domain = org.myai
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.3
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,requests,urllib3,chardet,idna,certifi,pyjnius,android
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
