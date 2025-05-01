# استيراد المكتبات المطلوبة
from flask import Flask, render_template, request, jsonify
import boto3
import os
import json
from werkzeug.utils import secure_filename
import logging
from botocore.exceptions import ClientError
from datetime import datetime

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إنشاء تطبيق Flask
app = Flask(__name__)

# إعدادات S3
S3_BUCKET = 'fcdsgirlsbucket'
S3_REGION = 'us-east-1'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf', 'txt'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit

# التأكد من وجود المجلد المؤقت
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# إعداد عميل S3
try:
    s3 = boto3.client('s3', region_name=S3_REGION)
except Exception as e:
    logger.error(f"خطأ في إعداد عميل S3: {e}")
    raise

# التحقق من سياسة الـ bucket وإعدادات CORS
def ensure_bucket_policy_and_cors():
    try:
        # سياسة الـ bucket للسماح بالوصول العام
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{S3_BUCKET}/*"
                }
            ]
        }
        s3.put_bucket_policy(Bucket=S3_BUCKET, Policy=json.dumps(bucket_policy))
        logger.info(f"تم تحديث سياسة الـ bucket '{S3_BUCKET}' للسماح بالوصول العام")

        # إعداد CORS
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST"],
                    "AllowedOrigins": ["*"],
                    "ExposeHeaders": [],
                    "MaxAgeSeconds": 3000
                }
            ]
        }
        s3.put_bucket_cors(Bucket=S3_BUCKET, CORSConfiguration=cors_configuration)
        logger.info(f"تم تحديث إعدادات CORS لـ bucket '{S3_BUCKET}'")
    except ClientError as e:
        logger.error(f"خطأ أثناء تحديث سياسة الـ bucket أو CORS: {e}")
        raise

# التحقق من امتداد الملف
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# التحقق من وجود الـ bucket وإعداداته عند بدء التطبيق
try:
    s3.head_bucket(Bucket=S3_BUCKET)
    ensure_bucket_policy_and_cors()  # تحديث السياسة و CORS
except ClientError as e:
    logger.error(f"خطأ في الوصول إلى الـ bucket: {e}")
    raise

# الصفحة الرئيسية
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# معالجة رفع الملف
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'لم يتم اختيار ملف'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'لم يتم اختيار ملف'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'نوع الملف غير مسموح به'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': 'حجم الملف كبير جدًا (الحد الأقصى 10 ميجابايت)'}), 400
        file.seek(0)

        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)

        try:
            file.save(filepath)
            s3.upload_file(
                Filename=filepath,
                Bucket=S3_BUCKET,
                Key=unique_filename,
                ExtraArgs={'ACL': 'public-read'}
            )
            download_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{unique_filename}"
            os.remove(filepath)
            logger.info(f"تم رفع الملف بنجاح: {unique_filename}")
            return jsonify({'download_url': download_url})

        except ClientError as e:
            logger.error(f"خطأ أثناء رفع الملف إلى S3: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f"فشل رفع الملف: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"خطأ غير متوقع: {e}")
        return jsonify({'error': 'حدث خطأ غير متوقع'}), 500

# جلب قائمة الملفات
@app.route('/files', methods=['GET'])
def list_files():
    try:
        response = s3.list_objects_v2(Bucket=S3_BUCKET)
        uploaded_files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                file_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{obj['Key']}"
                uploaded_files.append({'name': obj['Key'], 'url': file_url})
        return jsonify({'files': uploaded_files})
    except ClientError as e:
        logger.error(f"خطأ أثناء جلب قائمة الملفات: {e}")
        error_message = str(e.response['Error']['Message']) if 'Error' in e.response else str(e)
        return jsonify({'error': f"فشل جلب قائمة الملفات: {error_message}"}), 500

# تشغيل التطبيق
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)