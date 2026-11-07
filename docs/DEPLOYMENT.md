# פריסה — מצב נוכחי

| רכיב | Vercel project | כתובת | מקור |
|---|---|---|---|
| API (FastAPI) | `control-center-api` | https://control-center-api-ten.vercel.app | `control-center/server` |
| UI (Vite) | `control-center` | https://control-center-nu-pied.vercel.app | `control-center/web` |
| מסד נתונים | Supabase project `pt` (eu-central-1) | session pooler `aws-1-eu-central-1.pooler.supabase.com:5432`, role `pt_app` | מיגרציות `server/pt_agent/db/migrations` |

ה-UI מפנה `/api/*` לשרת (rewrite ב-`web/vercel.json`), כך שהדפדפן רואה origin אחד.
Vercel Authentication כבוי בשני הפרויקטים: האפליקציה אוכפת כניסה בעצמה (bearer sessions).

## משתני סביבה בשרת (`control-center-api`)

| משתנה | סטטוס | הערה |
|---|---|---|
| `PT_ALLOW_SELF_REGISTER=0` | מוגדר | הרשמה פתוחה כבויה; מנהל מוסיף משתמשים ממסך המשתמשים |
| `DATABASE_URL` | מוגדר | `postgresql://pt_app.<project-ref>:<סיסמה>@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require` (ה-pooler דורש את מזהה הפרויקט בשם המשתמש) |
| `CC_SECRET_KEY` | מוגדר | מפתח Fernet להצפנת סודות חיבורים ומפתחות ספק |
| `PT_ORG_HMAC_KEY` | מוגדר | מפתח חדש (7.11.2026); טביעות אצבע של ראיות ישנות מהפריסה הקודמת לא יתאימו לחדשות |
| `CRON_SECRET` | מוגדר | מאמת את ה-cron `*/15 * * * *` ל-`/cc/sync/all` |

אומת: `GET /healthz` מחזיר `"storage":"postgres"`, `"secrets":true` ו-`migrations.ran=true`,
וגם `GET /api/healthz` דרך ה-UI. סיסמת תפקיד ה-DB `pt_app` סובבה ב-7.11.2026 ועודכנה
גם בפרויקט `pt` הישן. הסיסמאות עצמן אינן ברפו.

## מסד הנתונים

מיגרציות 0001–0005 הוחלו על Supabase `pt` ורשומות ב-`schema_migrations`.
המלאי נזרע (2 מרחבים, 95 פרויקטים, 178 נכסים, 178 שיוכים, 0 לא משויכים)
עם מזהים דטרמיניסטיים, כך ש-`python scripts/seed_inventory.py --dsn ...` ניתן להרצה חוזרת.

## מה עוד פתוח

1. רפו GitHub נפרד `lironbek/control-center` — צריך להיווצר ידנית (ריק); אחר כך
   `git push` מהעותק המקומי ולחבר אליו את שני פרויקטי ה-Vercel (Settings → Git).
   עד אז הקוד חי ב-`lironbek/cars` תחת `control-center/` על ענף `ccr-10d35ca5-rgi5eg`.
2. ענף ייצור ב-Vercel הוא `main`; הפריסות נוצרו ידנית מהענף. אחרי מיזוג ל-`main`
   כל push יפרוס אוטומטית.
3. הספרייה `pt/` ברפו `cars` היא הגרסה הישנה של המודול; הגרסה החיה היא
   `control-center/server/pt_agent`.
