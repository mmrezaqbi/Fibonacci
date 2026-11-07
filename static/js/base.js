 (function () {
      var form = document.getElementById('loginForm');
      var pw = document.getElementById('id_password');
      var toggle = document.getElementById('togglePw');
      var caps = document.getElementById('capsWarn');
      var btn = document.getElementById('submitBtn');

      // نمایش/مخفی کردن گذرواژه (type="button" است و فرم را ارسال نمی‌کند)
      toggle.addEventListener('click', function () {
        pw.type = pw.type === 'password' ? 'text' : 'password';
        pw.focus();
      });

      // هشدار Caps Lock
      function checkCaps(e) {
        if (e.getModifierState) caps.classList.toggle('show', e.getModifierState('CapsLock'));
      }
      pw.addEventListener('keyup', checkCaps);
      pw.addEventListener('keydown', checkCaps);
      pw.addEventListener('blur', function () { caps.classList.remove('show'); });

      // حالت بارگذاری: هیچ preventDefault یا بازنویسی ارسال فرم وجود ندارد.
      // تغییر ظاهر دکمه با تأخیر انجام می‌شود تا ارسال طبیعی مرورگر دخالتی نشود.
      form.addEventListener('submit', function () {
        setTimeout(function () {
          btn.classList.add('loading');
          btn.querySelector('.label').textContent = 'در حال ورود...';
        }, 0);
      });

      // اگر کاربر با دکمه «بازگشت» برگشت، حالت دکمه ریست شود
      window.addEventListener('pageshow', function (e) {
        if (e.persisted) {
          btn.classList.remove('loading');
          btn.querySelector('.label').textContent = 'ورود';
        }
      });
    })();