# מרכז הבקרה — Control Center

מרכז בקרה פרטי בעברית לפרויקטים, סשני עבודה ואוטומציות, עם מודול סקרי אבטחה
מורשים (PT) בתוכו. רפו אחד, שרת אחד, מסד נתונים אחד.

| חלק | מה זה | איפה |
|---|---|---|
| `server/` | FastAPI אחד. `pt_agent/` הליבה המשותפת (אימות, תפקידים, אחסון, מיגרציות) ומודול הסקרים; `cc/` מרכז הבקרה | Python 3.12 |
| `web/` | React + Vite + Tailwind, RTL. מסכי מרכז הבקרה ומסכי הסקרים תחת "סקרי אבטחה" | TypeScript |
| `docs/` | האפיונים (מרכז הבקרה v2, PT v1.1), המוקאפ, ארכיטקטורה, קריטריוני קבלה, [סקירת האבטחה והנכונות](docs/REVIEW-2026-11-07.md) ו[מצב הפריסה](docs/DEPLOYMENT.md) ו[שימוש לפי לקוח](docs/USAGE.md) | |

## מה יש בפנים

**מרכז הבקרה** (אפיון v2): מרחבים עם הרשאות (מנהל/עורך/צופה), פרויקטים עם
לשוניות סקירה / נכסים / סשנים / כלים ומפתחות / עלויות / סוכנים / סקרי אבטחה,
חיבורים לספקים (GitHub, Vercel, Supabase, n8n) עם אימות הרשאה לפני שמירה,
סנכרון ידני ומתוזמן (cron כל 15 דקות), קטלוג נכסים עם תיאור ידני שנשמר,
פיד פעילות, תיבת מיון עם הצעות שיוך לפי קישור יציב, סשני עבודה עם ציר אירועים
והצעות שיוך (בלי שיוך אוטומטי לפי שעה), מדווח חיצוני חתום עם מניעת כפילויות,
התראות (כשל בייצור, עיכוב סנכרון, הרשאה), פנקס עלויות (חיוב מדווח / אומדן /
הקצאה / מנוי) ומפתחות ספק מוצפנים עם סבב, ומרכז סוכנים בקריאה-בלבד עם ריצות,
תקציב, idempotency ותיעוד עלות.

**סקרי אבטחה** (אפיון PT): חוזה בדיקה, מנוע מדיניות, אכיפת יעדים ו-DNS,
ריצה חיה, ממצאים, כספת ראיות מושחרות, דוחות, ביקורת. ראו `docs/PT_ARCHITECTURE.md`.

## הרצה מקומית

```bash
# server
cd server && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export CC_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
uvicorn app:app --port 8000 --reload
python -m pytest -q            # 117 בדיקות; PT_TEST_DATABASE_URL מפעיל בדיקות Postgres

# web
cd web && npm install && npm run dev     # מפנה /api ל-localhost:8000
npm run build
node e2e/cc.spec.cjs http://localhost:5173 e2e/shots-cc      # זרימת מרכז הבקרה בדפדפן
node e2e/flow.spec.cjs http://localhost:5173 target.test:8081 e2e/shots   # זרימת PT (דורש יעד מעבדה, ראו web/e2e/target_server.py)
```

## משתני סביבה (שרת)

| משתנה | תפקיד |
|---|---|
| `DATABASE_URL` | Postgres (Supabase/Neon). בלי זה: אחסון בזיכרון |
| `CC_SECRET_KEY` | מפתח Fernet להצפנת טוקנים ומפתחות. חובה לחיבורים ולמפתחות |
| `PT_ORG_HMAC_KEY` | טביעות HMAC לראיות (PT סעיף 10) |
| `CRON_SECRET` | מאמת את ה-cron של Vercel ל-`/cc/sync/all` |
| `ANTHROPIC_API_KEY` | אופציונלי. מפתח סביבה לסוכנים כשאין מפתח מרחב |
| `PT_ALLOW_SELF_REGISTER` | `0` נועל פתיחת ארגון חדש מהאתר |
| `PT_AUTO_MIGRATE` | `1` (ברירת מחדל) מריץ מיגרציות בעלייה |

המיגרציות ב-`server/pt_agent/db/migrations/` (0001 PT, 0002 אימות, 0003 מרכז הבקרה)
רצות אוטומטית בעלייה הראשונה מול Postgres.

## פריסה

שני פרויקטים ב-Vercel מאותו רפו: `server/` (FastAPI preset, `main.py`) ו-`web/`
(Vite). `web/vercel.json` מפנה `/api/*` לשרת כך שהאפליקציה נשארת same-origin.
הדמו (נתונים סינתטיים) הוא `docs/Project_Control_Center_Mockup_HE.html`, ללא גישה
לתשתית.
