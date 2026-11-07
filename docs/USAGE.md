# שימוש לפי לקוח — מדידת צריכת API, הודעות ו-OCR

## מה זה פותר

לכל לקוח יש אינטגרציות שצורכות שירותים בתשלום: קריאות ל-Claude / Gemini / OpenAI,
עמודי OCR, הודעות WhatsApp (ולכמה נמענים), SMS. מרכז הבקרה שומר **רשומת שימוש**
לכל קריאה כזו ומציג לפי לקוח, ספק, ממשק (מי ביצע את הקריאה) ופרויקט, לתקופה.

## מודל הנתונים (מיגרציה 0006)

| טבלה | תפקיד |
|---|---|
| `clients` | לקוח במרחב: שם, מזהה חיצוני (CRM), הערות. ייחודי לפי שם במרחב. נוצר ידנית או אוטומטית בדיווח הראשון בשמו |
| `usage_entries` | רשומה אחת = מדד אחד: `provider`, `metric`, `quantity`, `unit`, `interface`, `model`, `client_id`, `project_id`, `external_id` (דה-דופ), `occurred_at` |
| `cc_projects.client_id` | פרויקט שייך ללקוח; שימוש שמדווח לפרויקט בלי לקוח נזקף ללקוח של הפרויקט |

ספקים: `claude`, `gemini`, `openai`, `ocr`, `whatsapp`, `telegram`, `sms`, `email`, `other`.
מדדים: `requests`, `tokens_in`, `tokens_out`, `tokens_cached`, `messages`, `recipients`, `pages`, `characters`, `minutes`, `units`.

## מאיפה מגיעים הנתונים

1. **דיווח מהאינטגרציה שמבצעת את הקריאה** (n8n, בוט WhatsApp, אפליקציה): `POST /cc/usage`
   עם טוקן הדיווח של המרחב (`X-Report-Token`, נוצר במסך "חיבורים"). זה המקור המרכזי:
   רק מי שמבצע את הקריאה יודע עבור איזה לקוח היא בוצעה ולכמה נמענים.
2. **ריצות סוכנים במערכת**: כל ריצה רושמת אוטומטית `requests`, `tokens_in`, `tokens_out`
   עם `interface = agent:<שם>` ללקוח של הפרויקט.
3. (עתידי) משיכה מ-API של הספקים (Anthropic Admin Usage, Google Cloud Billing): נותן
   סך לפי מפתח/פרויקט ספק, לא לפי לקוח; ישמש להתאמה (reconciliation) מול הדיווחים.

## חוזה הדיווח

```
POST https://master-auto-lake.vercel.app/api/cc/usage
X-Report-Token: <token>
Content-Type: application/json

{
  "workspace_id": "ws_...",
  "entries": [
    {"provider": "whatsapp", "metric": "messages", "quantity": 12, "recipients": 5,
     "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "wa-run-123",
     "occurred_at": "2026-11-07T10:00:00Z"},
    {"provider": "gemini", "metric": "requests", "quantity": 30, "model": "gemini-2.5-pro",
     "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "gm-run-123"},
    {"provider": "claude", "metric": "tokens_in", "quantity": 1200, "model": "claude-sonnet-5-5",
     "interface": "app/crm", "project_id": "prj_...", "external_id": "cl-run-7:in"},
    {"provider": "ocr", "metric": "pages", "quantity": 40, "interface": "app/crm", "client": "לקוח ב"}
  ]
}
```

כללים: `client` (שם) או `client_id`; אם יש `project_id` בלי לקוח, נלקח לקוח הפרויקט.
`recipients` על רשומת הודעות נשמר כמדד נפרד "נמענים". `external_id` חוזר = כפילות
(התשובה מחזירה `accepted` / `duplicates`). עד 500 רשומות לבקשה.

מתוך האפליקציות שלך (Next.js / Vite / Node / Python): העתק את `docs/snippets/report-usage.ts`
או `docs/snippets/report_usage.py`, הגדר `CC_USAGE_URL`, `CC_REPORT_TOKEN`, `CC_WORKSPACE_ID`,
וקרא ל-`reportUsage()` מיד אחרי כל קריאה בתשלום (יש עטיפות מוכנות ל-Claude, Gemini,
WhatsApp ו-OCR). הדיווח אסינכרוני ולעולם לא מפיל את המוצר. `external_id` ייחודי לכל
קריאה, כך שניסיון חוזר לא נספר פעמיים.

## תצוגה

מסך "שימוש לפי לקוח": מסננים (לקוח, ספק, תקופה; ברירת מחדל החודש הנוכחי), אריחים
(קריאות, טוקנים, הודעות + נמענים, עמודי OCR), טבלאות לפי לקוח (עם פירוט לפי ספק
וממשק), לפי ממשק, לפי ספק ופרויקט, רשומות אחרונות, וניהול לקוחות. בעמוד פרויקט:
הלקוח והשימוש החודשי של הפרויקט. `GET /cc/usage` מחזיר את אותו דוח ל-API.
