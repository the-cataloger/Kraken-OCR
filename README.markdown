```
       # Kraken OCR GUI

       ## Overview
       تطبيق واجهة مستخدم رسومية مبني بـ Python و PySide6 لتشغيل وتدريب Kraken OCR. يدعم تجزئة الصور، استخراج النصوص، وتدريب نماذج OCR جديدة لمعالجة المخطوطات والنصوص الممسوحة ضوئيًا. A Python GUI app for Kraken OCR, supporting image segmentation, text extraction, and model training.

       ## Features
       - **تجزئة الصور**: عرض خطوط أساسية (baselines) على الصور المجزأة.
       - **استخراج النصوص**: التعرف الضوئي باستخدام نماذج Kraken.
       - **تدريب نماذج**: إنشاء نماذج OCR مخصصة باستخدام أزواج صور ونصوص.
       - واجهة سهلة تدعم اللغتين العربية والإنجليزية.

       ## Requirements
       - Python 3.x
       - مكتبات Python: `PySide6`, `Pillow`
       - تثبيت Kraken OCR (`kraken` و `ketos`). راجع: [Kraken Installation](https://kraken.re)
       - نظام تشغيل: Windows/Linux/MacOS

       ### تثبيت المتطلبات
       ```bash
       pip install PySide6 Pillow
       ```

       ## Installation
       1. تأكد من تثبيت Python 3.x.
       2. قم بتثبيت Kraken وفقًا للتعليمات الرسمية.
       3. قم بتثبيت المكتبات المطلوبة باستخدام الأمر أعلاه.
       4. استنسخ هذا المستودع:
          ```bash
          git clone https://github.com/YourUsername/Kraken-OCR-GUI.git
          ```
       5. شغّل التطبيق:
          ```bash
          python kraken_gui.py
          ```

       ## How to Use
       ### تبويب التعرف الضوئي (OCR):
       1. حدد مسار مجلد Kraken/Ketos.
       2. اختر صورة (png، jpg، tiff، إلخ).
       3. انقر على "تجزئة الصورة" لتحليل الصورة.
       4. أدخل اسم نموذج OCR (مثل `arabic_best.mlmodel`).
       5. انقر على "استخراج النص" لعرض النص المستخرج.

       ### تبويب تدريب نموذج:
       1. أضف أزواج (صورة + نص كتابي).
       2. أدخل اسم النموذج الناتج وعدد الحقب (epochs).
       3. انقر على "بدء التدريب" لإنشاء نموذج جديد.

       ## Author
       - **The Cataloger**
       - Email: manuscriptscataloger@gmail.com
       ```