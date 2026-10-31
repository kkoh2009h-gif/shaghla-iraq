# خادم شَغلة

خادم مستقل باستخدام FastAPI وSQLAlchemy. لا يستخدم Supabase أو Firebase.

## تشغيل محلي
1. ادخل مجلد `backend`.
2. ثبّت الحزم: `pip install -r requirements.txt`.
3. عيّن أسرار المصادقة ومتغيرات SMS كما بالأسفل.
4. شغّل: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
5. افتح `/docs` لتجربة الواجهات.

## إعدادات الخادم المطلوبة
- `DATABASE_URL`: رابط قاعدة البيانات. SQLite للتطوير فقط، وPostgreSQL موصى به للإنتاج.
- `GOOGLE_WEB_CLIENT_ID`: معرّف OAuth Web client المستخدم للتحقق من Google ID tokens.
- `SHAGHLA_AUTH_SECRET`: مفتاح عشوائي طويل (32 بايت على الأقل) لتوقيع جلسات الدخول وتجزئة OTP. لا تضعه في GitHub أو التطبيق.
- `SMS_GATEWAY_URL`: عنوان API لمزود رسائل SMS.
- `SMS_GATEWAY_TOKEN`: رمز API الخاص بمزود الرسائل.

بوابة الرسائل يجب أن تقبل طلب POST بصيغة JSON: `{"to":"+9647xxxxxxxxx","message":"..." }` مع ترويسة `Authorization: Bearer <token>`، وأن تعيد HTTP 2xx عند قبول الرسالة. هذا عقد تكامل عام؛ يجب تكييفه مع توثيق مزود الرسائل الفعلي. من دون إعداد SMS لن يصدر الخادم رمزاً تجريبياً ولن يعيده في الاستجابة.

## تسجيل الدخول باستخدام Google
- `POST /auth/google`: يستقبل Google ID token والدور `worker` أو `employer`.
- يحقق الخادم من التوقيع والجمهور `GOOGLE_WEB_CLIENT_ID` ومن أن البريد موثّق قبل إصدار جلسة شَغلة.
- لا ترسل Google ID token إلا عبر HTTPS، ولا تثق به قبل التحقق من الخادم.
- أضف `GOOGLE_WEB_CLIENT_ID` إلى إعدادات بيئة الخادم من Web OAuth Client ID في Google Cloud.

## المصادقة والحسابات
- `POST /auth/request-otp`: يطلب رمزاً لرقم عراقي ودور `worker` أو `employer`.
- `POST /auth/verify-otp`: يتحقق من الرمز ويعيد Bearer token.
- `GET /auth/me`: يعرض الحساب الحالي.
- `PATCH /auth/me`: يحدّث الاسم الكامل.
- الرمز صالح 5 دقائق، ويُسمح بخمس محاولات، وطلب رمز جديد بعد 60 ثانية.
- صيغة الهاتف المقبولة: `07xxxxxxxxx` أو `+9647xxxxxxxxx`.

## الوظائف والتقديم
- `GET /jobs`: بحث وفلاتر محافظة وتصنيف ونوع عمل ونطاق أجر مع ترقيم.
- `GET /jobs/{id}`: تفاصيل وظيفة نشطة.
- `POST /jobs`: يتطلب حساب صاحب عمل مسجل الدخول.
- `GET /employer/jobs`: وظائف صاحب العمل الحالي فقط.
- `POST /jobs/{id}/apply`: يتطلب حساب عامل مسجل الدخول.
- `GET /worker/applications`: طلبات العامل الحالي.\n- `GET /employer/jobs/{id}/applications`: المتقدمون لوظيفة يملكها صاحب العمل.\n- `PATCH /employer/applications/{id}`: تحديث حالة الطلب إلى قيد المراجعة أو مقبول أو مرفوض.\n- `POST /worker/applications/{id}/withdraw`: سحب طلب العامل.\n- `POST /employer/jobs/{id}/close`: إغلاق وظيفة يملكها صاحب العمل.
- معرّف صاحب العمل والعامل يؤخذ من الجلسة الموقعة، وليس من جسم الطلب.

## الاختبارات
من مجلد `backend`: `pytest -q`. الاختبارات تستبدل إرسال SMS بدالة اختبار داخلية ولا ترسل رسائل حقيقية.

## ما يزال مطلوباً قبل الإطلاق العام
- اختيار مزود SMS فعلي يدعم أرقام العراق +964، ثم تهيئة متغيراته في بيئة الاستضافة.
- PostgreSQL، وترحيلات Alembic، ونسخ احتياطي ومراقبة.
- تحديد معدل الطلبات على مستوى IP والهاتف، حماية من إساءة الاستخدام، وسجل تدقيق.
- مراجعة أمنية مستقلة، سياسة خصوصية وشروط استخدام، وآلية حذف الحساب.
- إدارة حالات الوظائف والطلبات، البلاغات، ولوحة الإدارة وصلاحياتها.
- ربط تطبيق Android بعنوان API منشور عبر HTTPS. GitHub Actions يبني APK ويشغّل الاختبارات، لكنه لا يستضيف API دائماً.

هذه نسخة تطوير متقدمة وليست تصريحاً بأنها جاهزة للنشر التجاري.

## تشغيل API مع PostgreSQL عبر Docker Compose

من جذر المستودع، أنشئ متغيرات البيئة في الطرفية (لا تحفظ الأسرار في Git):

```bash
export POSTGRES_PASSWORD='ضع-كلمة-مرور-طويلة-هنا'
export SHAGHLA_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose up --build -d
docker compose logs -f api
```

بعد التشغيل، اختبر `http://localhost:8000/health` وافتح `http://localhost:8000/docs` للتطوير فقط. قبل تعريض الخادم للإنترنت، استخدم HTTPS عبر reverse proxy أو منصة استضافة، واضبط أسرار SMS من لوحة الاستضافة. لا تفتح منفذ PostgreSQL للعامة. خذ نسخاً احتياطية واختبر استعادتها.

> ملاحظة: هذا إعداد تشغيل ذاتي الاستضافة، وليس نشرًا عامًا تلقائيًا. كما أن تهيئة PostgreSQL لا تنشئ ترحيلات Alembic بعد؛ يلزم إعداد migrations قبل تحديثات قاعدة البيانات الإنتاجية.
