// Browser E2E: the full professor + TA workflow through the real UI and API.
//
// Prerequisites (see README "Testing"): API on :8000 and web on :3000 against a
// migrated database, Tesseract installed, a professor account, and fixtures:
//   python -m scripts.create_user --email e2e.prof@uni.edu --role professor --password e2e-prof-pass-1
//   python -m scripts.e2e_fixtures /tmp/gradeops-e2e
//   E2E_FILES=/tmp/gradeops-e2e npm run e2e
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const WEB = process.env.E2E_WEB || "http://localhost:3000";
const CODE = `CS${3000 + (Date.now() % 900)}`;
const FILES = process.env.E2E_FILES || "/tmp/gradeops-e2e";
const SHOTS = process.env.E2E_SHOTS || path.join(require("os").tmpdir(), "gradeops-e2e-shots");
fs.mkdirSync(SHOTS, { recursive: true });

const log = (...a) => console.log("•", ...a);
async function shot(page, name) {
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}
async function login(page, email, password, { stay = false } = {}) {
  if (!stay) await page.goto(`${WEB}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

let current;
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  current = page;
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));

  // ---- Unauthenticated access is redirected to login
  await page.goto(`${WEB}/professor/exams`);
  await page.waitForURL(/\/login\?next=%2Fprofessor%2Fexams/);
  log("anonymous → /login?next=… ok");

  // ---- Professor: login → dashboard
  await login(page, "e2e.prof@uni.edu", "e2e-prof-pass-1", { stay: true });
  await page.waitForURL(/\/professor\/exams$/); // honours next=
  await page.goto(`${WEB}/professor`);
  await page.getByText("Active courses", { exact: true }).waitFor();
  log("professor login → /professor ok");

  // ---- Create course
  await page.goto(`${WEB}/professor/courses`);
  await page.getByRole("button", { name: "New course" }).click();
  await page.getByLabel("Course code").fill(CODE);
  await page.getByLabel("Course name").fill("Data Structures");
  await page.getByLabel("Semester").fill("Autumn");
  await page.getByLabel("Academic year").fill("2026-27");
  await page.getByRole("dialog").getByRole("button", { name: "Create course" }).click();
  await page.getByText(CODE, { exact: true }).locator("..").getByRole("link", { name: "Data Structures" }).click();
  await page.waitForURL(/\/professor\/courses\/[0-9a-f-]+$/);
  const courseUrl = page.url();
  const courseId = courseUrl.split("/").pop();
  log("course created", courseId);

  // ---- Roster via CSV
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: /Students/ }).click();
  await page.locator('input[type="file"][accept*=".csv"]').setInputFiles(path.join(FILES, "roster.csv"));
  await page.getByText(/^3 enrolled ·/).waitFor();
  await page.getByRole("cell", { name: "E2E003" }).waitFor();
  log("roster imported");

  // ---- Add TA (create account)
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: /TAs/ }).click();
  await page.getByRole("button", { name: "Add TA" }).click();
  await page.getByLabel("TA email").fill("e2e.ta@uni.edu");
  await page.getByLabel(/Create a new TA account/).check();
  await page.getByLabel("Full name").fill("Rahul Verma");
  await page.getByLabel(/Initial password/).fill("e2e-ta-pass-1");
  await page.getByRole("dialog").getByRole("button", { name: "Add TA" }).click();
  await page.getByRole("cell", { name: /Rahul Verma/ }).waitFor();
  log("TA added");

  // ---- Create exam via wizard
  await page.goto(`${WEB}/professor/exams/new?course=${courseId}`);
  await page.getByLabel("Exam name").fill("Mid Semester Examination");
  await page.getByLabel("Date").fill("2026-09-20");
  await page.getByLabel("Maximum marks").fill("20");
  await shot(page, "05-create-exam");
  await page.getByRole("button", { name: /Create exam/ }).click();
  await page.waitForURL(/step=1/);
  await page.locator('input[type="file"][accept*=".json"]').setInputFiles(path.join(FILES, "ds_midsem_rubric.json"));
  await page.getByText(/4 questions · 20 marks/).waitFor();
  await page.getByRole("button", { name: "Continue to answer sheets" }).click();
  await page.waitForURL(/step=2/);
  await page.locator('input[type="file"][multiple]').setInputFiles(["E2E001_midsem.pdf", "E2E002_midsem.pdf", "E2E003_midsem.pdf"].map((f) => path.join(FILES, f)));
  await page.getByRole("button", { name: "Upload 3 of 3" }).waitFor();
  await shot(page, "06-upload-mapping");
  await page.getByRole("button", { name: "Upload 3 of 3" }).click();
  await page.getByText(/3 answer sheet\(s\) uploaded/).first().waitFor();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/step=3/);
  await page.getByRole("button", { name: /Evaluate 3 submissions/ }).click();
  await page.getByText(/Latest job · completed/).waitFor({ timeout: 120000 });
  log("AI evaluation completed");
  await page.getByRole("link", { name: "Open exam dashboard" }).click();
  await page.waitForURL(/\/professor\/exams\/[0-9a-f-]+$/);
  const examUrl = page.url();

  // ---- Assign the TA to the exam
  await page.getByLabel("Assign a TA").selectOption({ label: "Rahul Verma" });
  await page.getByRole("button", { name: "Unassign Rahul Verma" }).waitFor();
  await page.reload(); // persistence: DB-backed state survives refresh
  await page.getByText("AI processed", { exact: true }).waitFor();
  await shot(page, "07-exam-command-center");
  log("TA assigned; exam dashboard ok");

  // ---- TA session
  const taCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const ta = await taCtx.newPage();
  ta.on("pageerror", (e) => errors.push(`ta pageerror: ${e.message}`));
  await login(ta, "e2e.ta@uni.edu", "e2e-ta-pass-1");
  await ta.waitForURL(/\/ta$/);
  await ta.getByText("Pending reviews", { exact: true }).waitFor();
  await ta.getByText("Mid Semester Examination", { exact: true }).first().waitFor();
  await shot(ta, "10-ta-overview");
  log("TA login → /ta ok");

  // TA cannot open professor area
  await ta.goto(`${WEB}/professor`);
  await ta.getByText("403 — Not permitted", { exact: true }).waitFor();
  await ta.waitForURL(/\/ta$/, { timeout: 10000 });
  log("TA blocked from /professor (403 → /ta)");

  await ta.goto(`${WEB}/ta/reviews`);
  await ta.getByRole("link", { name: "Open review" }).first().waitFor();
  await shot(ta, "11-ta-review-queue");
  await ta.getByRole("link", { name: "Open review" }).first().click();
  await ta.waitForURL(/\/ta\/reviews\/[0-9a-f-]+$/);
  await ta.getByText("AI explanation", { exact: true }).waitFor();
  await ta.getByRole("img", { name: /Handwritten answer/ }).waitFor();
  await shot(ta, "12-ta-review-screen");
  const firstUrl = ta.url();

  // Approve with keyboard → auto-advance
  await ta.keyboard.press("a");
  await ta.waitForURL((u) => u.toString() !== firstUrl);
  await ta.getByText("AI explanation", { exact: true }).waitFor();
  log("approve via 'A' → advanced");

  // Override with keyboard
  const secondUrl = ta.url();
  await ta.keyboard.press("o");
  const dlg = ta.getByRole("dialog", { name: "Override marks" });
  await dlg.waitFor();
  const firstInput = dlg.locator('input[type="number"]').first();
  await firstInput.fill("99");
  await dlg.getByText(/Maximum is 5/).waitFor();
  await firstInput.fill("2");
  await dlg.getByLabel(/Reason/).fill("Partial working shown in the margin");
  await shot(ta, "13-ta-override");
  await dlg.getByRole("button", { name: /Save/ }).click();
  await ta.waitForURL((u) => u.toString() !== secondUrl);
  log("override saved → advanced");

  // Escalate with keyboard
  await ta.getByText("AI explanation", { exact: true }).waitFor();
  await ta.keyboard.press("e");
  const esc = ta.getByRole("dialog", { name: "Escalate to professor" });
  await esc.getByLabel(/Reason/).selectOption("ocr_unreliable");
  await esc.getByLabel(/Notes/).fill("Q3 handwriting is unclear");
  await esc.getByRole("button", { name: "Escalate" }).click();
  await ta.getByText(/Escalated to the professor/).waitFor();
  log("escalated");

  await ta.goto(`${WEB}/ta/history`);
  await ta.getByRole("cell", { name: /Escalated|Overridden|Approved/ }).first().waitFor();
  await shot(ta, "14-ta-history");
  const historyRows = await ta.locator("tbody tr").count();
  log("TA history rows:", historyRows);

  // ---- Professor resolves escalation
  await page.goto(`${WEB}/professor/reviews/escalated`);
  await page.getByRole("link", { name: "Inspect & resolve" }).first().waitFor();
  await shot(page, "08-escalations");
  await page.getByRole("link", { name: "Inspect & resolve" }).first().click();
  await page.getByRole("button", { name: "Resolve escalation" }).click();
  const res = page.getByRole("dialog", { name: "Resolve escalation" });
  await res.getByLabel(/Notes/).fill("Checked the original scan; AI grade stands.");
  await res.getByRole("button", { name: "Resolve & approve" }).click();
  await page.getByText(/Escalation resolved/).waitFor();
  log("escalation resolved");

  // ---- Finalise: approve → lock → publish
  await page.goto(examUrl);
  const approveBtn = page.getByRole("button", { name: "Approve exam" });
  await approveBtn.waitFor();
  if (await approveBtn.isDisabled()) throw new Error("Approve disabled: " + (await page.locator("section", { hasText: "Finalisation" }).innerText()));
  await approveBtn.click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve all grades" }).click();
  await page.getByRole("button", { name: "Lock grades" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Lock grades" }).click();
  await page.getByRole("button", { name: "Publish grades" }).click();
  const pub = page.getByRole("dialog", { name: "Publish grades" });
  await pub.getByText("Submissions", { exact: true }).first().waitFor();
  await shot(page, "09-publish-summary");
  const ack = pub.getByRole("checkbox");
  if (await ack.count()) await ack.check();
  await pub.getByRole("button", { name: "Publish grades" }).click();
  await page.locator("h1", { hasText: "Published" }).waitFor();
  log("published");

  // ---- Gradebook + CSV export + refresh persistence
  await page.goto(`${examUrl}/gradebook`);
  await page.getByRole("cell", { name: "E2E001" }).waitFor();
  await page.reload();
  await page.getByText(/final grades/).waitFor();
  await shot(page, "03-gradebook");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export final gradebook" }).click()]);
  const csv = fs.readFileSync(await download.path(), "utf8");
  if (!csv.includes("E2E002") || !csv.startsWith("student_id")) throw new Error("bad CSV: " + csv.slice(0, 200));
  log("final CSV exported:", download.suggestedFilename());

  // ---- Overview / analytics screenshots (light + dark)
  await page.goto(`${WEB}/professor`);
  await page.getByText("Recent activity", { exact: true }).waitFor();
  await shot(page, "01-professor-overview");
  await page.goto(`${examUrl}/analytics`);
  await page.getByText("Question difficulty", { exact: true }).waitFor();
  await shot(page, "04-exam-analytics");
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  await shot(page, "04b-exam-analytics-light");
  await page.goto(`${courseUrl}/tas`);
  await page.getByRole("cell", { name: /Rahul Verma/ }).waitFor();
  await shot(page, "02-course-tas-light");

  await browser.close();
  const relevant = errors.filter((e) => !/favicon|Failed to fetch RSC payload|Failed to load resource: the server responded with a status of 40[134]/.test(e));
  if (relevant.length) {
    console.log("Browser errors:\n" + relevant.join("\n"));
    process.exitCode = 1;
  } else console.log("E2E PASSED — no browser errors");
})().catch(async (e) => {
  console.error("E2E FAILED:", e);
  if (current) await current.screenshot({ path: path.join(SHOTS, "FAILURE.png"), fullPage: true }).catch(() => {});
  process.exit(1);
});
