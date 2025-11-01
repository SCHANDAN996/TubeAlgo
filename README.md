हाँ, ज़रूर। यहाँ आपके लिए सभी निर्देशों की एक `QUICK_REFERENCE.md` फ़ाइल है। आप इस पूरे कोड को कॉपी करके अपने प्रोजेक्ट में एक नई फ़ाइल बनाकर सेव कर सकते हैं।

````markdown
# TubeAlgo - सेटअप और डिप्लॉयमेंट क्विक गाइड

यह एक क्विक गाइड है जो आपको अलग-अलग प्लेटफॉर्म पर प्रोजेक्ट को सेटअप और रन करने में मदद करेगी।

---
## 1. विंडोज पर लोकल सेटअप और रन करें
ज़रूर, अपने प्रोजेक्ट को VS Code में फिर से चलाने के लिए आपको तीन टर्मिनल में ये कमांड्स चलाने होंगे:

### 1\. पहला टर्मिनल (Python Flask Server)

यह आपके मुख्य एप्लीकेशन सर्वर को शुरू करेगा।

```bash
python run.py
```

-----

### 2\. दूसरा टर्मिनल (Tailwind CSS)

यह आपकी CSS फ़ाइलों को देखेगा और बदलाव होने पर उन्हें ऑटोमेटिकली अपडेट करेगा।

```bash
npm run dev
```

-----

### 3\. तीसरा टर्मिनल (Celery Worker)

यह आपके बैकग्राउंड टास्क्स (जैसे नया प्रतियोगी जोड़ने के बाद डेटा एनालिसिस) को चलाएगा।

```bash
celery -A tubealgo.celery_utils.celery worker --loglevel=info
```

इन तीनों को चलाने के बाद आपका प्रोजेक्ट पूरी तरह से काम करने लगेगा।





### **सेटअप कमांड्स (सिर्फ एक बार चलाने हैं)**
```bash
# 1. प्रोजेक्ट डाउनलोड करें और फोल्डर में जाएं
git clone <your-repository-url>
cd tubealgo-flask-app-main

# 2. वर्चुअल एनवायरनमेंट बनाएं और एक्टिवेट करें
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. सभी Python और Node पैकेज इंस्टॉल करें
pip install -r requirements.txt
npm install

# 4. .env फ़ाइल बनाएं और अपनी सभी API Keys डालें

# 5. CSS/JS फाइलों को बिल्ड करें
npm run build
````

### **ऐप चलाने के लिए कमांड्स (हर बार चलाने हैं)**

आपको **4 अलग-अलग टर्मिनल** खोलने होंगे:

  * **टर्मिनल 1 (Redis):**

      * स्टार्ट मेनू से **"Redis Server"** चलाएं और चलने दें।

  * **टर्मिनल 2 (Celery Worker):**

    ```powershell
    .\venv\Scripts\Activate.ps1
    celery -A tubealgo.celery worker --loglevel=info
    ```

  * **टर्मिनल 3 (Celery Beat):**

    ```powershell
    .\venv\Scripts\Activate.ps1
    celery -A tubealgo.celery beat --loglevel=info
    ```

  * **टर्मिनल 4 (Flask App):**

    ```powershell
    .\venv\Scripts\Activate.ps1
    $env:FLASK_APP = "run.py"
    flask run
    ```

-----

## 2\. Render पर डिप्लॉय करें

1.  अपना पूरा कोड **GitHub** पर पुश करें।
2.  Render डैशबोर्ड पर जाएं -\> **New** -\> **Blueprint**।
3.  अपनी GitHub रिपॉजिटरी को कनेक्ट करें। Render आपकी `render.yaml` फ़ाइल को अपने आप पढ़ लेगा।
4.  **सबसे ज़रूरी:** एप्लीकेशन बनने के बाद, **Environment** टैब में जाएं।
5.  वहाँ पर अपनी सभी सीक्रेट कीज (`DATABASE_URL`, `REDIS_URL` को छोड़कर, क्योंकि वे Render खुद देगा) एक-एक करके डालें।
6.  सेटिंग्स सेव करें। Render अपने आप सब कुछ डिप्लॉय कर देगा।

-----

## 3\. Hostinger VPS पर डिप्लॉय करें (Ubuntu)

### **सर्वर सेटअप (सिर्फ एक बार)**

```bash
# सर्वर में SSH करें
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv nginx git redis-server -y
curl -fsSL [https://deb.nodesource.com/setup_20.x](https://deb.nodesource.com/setup_20.x) | sudo -E bash -
sudo apt-get install -y nodejs
```

### **प्रोजेक्ट सेटअप (सिर्फ एक बार)**

```bash
# प्रोजेक्ट डाउनलोड करें और फोल्डर में जाएं
git clone <your-repository-url>
cd tubealgo-flask-app-main

# एनवायरनमेंट सेटअप करें
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# CSS/JS बिल्ड करें
npm install
npm run build

# सर्वर पर .env फ़ाइल बनाएं और अपनी Production Keys डालें
nano .env
```

### **सर्विसेज चलाएं और मैनेज करें**

(यह मानते हुए कि आपने `systemd` और `Nginx` की फाइलें बना ली हैं)

```bash
# सभी सर्विसेज को पहली बार शुरू करने के लिए
sudo systemctl start redis-server tubealgo-web tubealgo-worker tubealgo-beat

# सर्वर रीबूट होने पर अपने आप शुरू करने के लिए
sudo systemctl enable redis-server tubealgo-web tubealgo-worker tubealgo-beat

# किसी सर्विस का स्टेटस जांचने के लिए (उदाहरण: वेब सर्वर)
sudo systemctl status tubealgo-web

# Nginx कॉन्फ़िगरेशन को टेस्ट और रीलोड करने के लिए
sudo nginx -t
sudo systemctl restart nginx
```

```
```