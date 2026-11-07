# פריסה — מצב נוכחי

| רכיב | Vercel project | כתובת | מקור |
|---|---|---|---|
| API (FastAPI) | `master-auto-api` | https://master-auto-api-lirons-projects-afcef793.vercel.app | `server/` ברפו `lironbek/master-auto`, ענף `main` |
| UI (Vite) | `master-auto` | https://master-auto-lake.vercel.app | `web/` ברפו `lironbek/master-auto`, ענף `main` |
| מסד נתונים | Supabase project `pt` (eu-central-1) | session pooler `aws-1-eu-central-1.pooler.supabase.com:5432`, role `pt_app` | מיגרציות `server/pt_agent/db/migrations` |

ה-UI מפנה `/api/*` לשרת (rewrite ב-`web/vercel.json`), כך שהדפדפן רואה origin אחד.
Vercel Authentication כבוי בשני הפרויקטים: האפליקציה אוכפת כניסה בעצמה (bearer sessions).

## משתני סביבה בשרת (`master-auto-api`)

| משתנה | סטטוס | הערה |
|---|---|---|
| `PT_ALLOW_SELF_REGISTER=0` | מוגדר | הרשמה פתוחה כבויה; מנהל מוסיף משתמשים ממסך המשתמשים |
| `DATABASE_URL` | מוגדר | `postgresql://pt_app.<project-ref>:<סיסמה>@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require` (ה-pooler דורש את מזהה הפרויקט בשם המשתמש) |
| `CC_SECRET_KEY` | מוגדר | מפתח Fernet להצפנת סודות חיבורים ומפתחות ספק |
| `PT_ORG_HMAC_KEY` | מוגדר | מפתח חדש (7.11.2026); טביעות אצבע של ראיות ישנות מהפריסה הקודמת לא יתאימו לחדשות |
| `CRON_SECRET` | מוגדר | מאמת את ה-cron `*/15 * * * *` ל-`/cc/sync/all` |
| `ANTHROPIC_API_KEY` | אופציונלי | מפתח ברירת מחדל לריצות סוכנים ולסריקות קוד כשלפרויקט אין מפתח משלו |
| `CC_SCAN_MODEL` | אופציונלי | מודל לסריקות קוד (ברירת מחדל claude-sonnet-5-5) |
| `CC_ALERT_WEBHOOK_URL` | אופציונלי | יעד POST להתראות ולסריקות עם ציון C |
| `RESEND_API_KEY`, `CC_ALERT_EMAIL_TO`, `CC_ALERT_EMAIL_FROM` | אופציונלי | התראות באימייל דרך Resend |
| `CC_PUBLIC_URL` | אופציונלי | קישור חזרה למערכת בתוך ההתראות |

אומת: `GET /healthz` מחזיר `"storage":"postgres"`, `"secrets":true` ו-`migrations.ran=true`,
וגם `GET /api/healthz` דרך ה-UI. סיסמת תפקיד ה-DB `pt_app` סובבה ב-7.11.2026 ועודכנה
גם בפרויקט `pt` הישן. הסיסמאות עצמן אינן ברפו.

## מסד הנתונים

מיגרציות 0001–0005 הוחלו על Supabase `pt` ורשומות ב-`schema_migrations`.
המלאי נזרע (2 מרחבים, 95 פרויקטים, 178 נכסים, 178 שיוכים, 0 לא משויכים)
עם מזהים דטרמיניסטיים, כך ש-`python scripts/seed_inventory.py --dsn ...` ניתן להרצה חוזרת.

## היסטוריה

הרפו הנפרד `lironbek/master-auto` הוא המקור מ-7.11.2026; כל push ל-`main` פורס
אוטומטית את שני הפרויקטים. העותק הקודם (`lironbek/cars` תחת `control-center/`, פרויקטי
Vercel `control-center` / `control-center-api`) נשאר להיסטוריה בלבד ואפשר למחוק אותו.
הספרייה `pt/` ב-`cars` והפרויקט `pt` ב-Vercel הם הגרסה הישנה של המודול.

## תקלה שתוקנה 7.11.2026: "Internal Server Error" אחרי הכניסה

הסיבה: טבלאות מרכז הבקרה (מיגרציות 0003–0005) הוחלו דרך קונסולת Supabase, ולכן
היו בבעלות `postgres` ולא `pt_app`. עם RLS מופעל וללא policies, תפקיד שאינו הבעלים
נחסם לגמרי (`permission denied for table workspaces`). התיקון: העברת הבעלות על כל
הטבלאות והרצפים ל-`pt_app`. כלל: מיגרציות מורצות ע"י השרת (auto-migrate כ-`pt_app`)
או, אם מריצים ידנית בקונסולה, מסיימים ב-`alter table <t> owner to pt_app`.
