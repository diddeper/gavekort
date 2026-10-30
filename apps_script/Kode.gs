/**
 * Gavekort – web app for activating and redeeming gift cards.
 *
 * Scanning a card's QR opens `<web app URL>?kode=<code>`. The page shows the card
 * and offers the next step: "Ikke solgt" → Aktiver → "Aktiv" → Løs inn → "Innløst".
 * Opening the page never changes anything; only the buttons do.
 *
 * Access control (all three must pass):
 *   1. Deployment: execute as the user accessing, anyone with a Google account.
 *   2. The spreadsheet is shared only with the allowed accounts.
 *   3. Script property ALLOWED_EMAILS (comma-separated) is checked on every call.
 *
 * Script properties (Project Settings → Script properties):
 *   ALLOWED_EMAILS   e.g. "her@gmail.com,me@gmail.com"
 *   BOOKING_URL      shown to anyone else who scans a card
 *   VALIDITY_MONTHS  optional, default 12
 */

const SHEET_NAME = 'Gavekort';
/** URL parameter with the card code. Never `c` or `sid`: Apps Script reserves them. */
const CODE_PARAM = 'kode';
const TIME_ZONE = 'Europe/Oslo';
const CODE_PATTERN = /^GK-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/;

/** Column headers, in order. Must match SHEET_COLUMNS in src/gavekort/batch.py. */
const HEADERS = [
  'Kode', 'Type', 'Format', 'Status', 'Generert', 'Aktivert',
  'Utløper', 'Innløst', 'Aktivert av', 'Innløst av', 'Notat',
];

/** 1-based column numbers, derived from HEADERS. */
const COL = Object.freeze({
  code: 1, type: 2, format: 3, status: 4, generated: 5, activated: 6,
  expires: 7, redeemed: 8, activatedBy: 9, redeemedBy: 10, note: 11,
});

const STATUS = Object.freeze({
  notSold: 'Ikke solgt',
  active: 'Aktiv',
  redeemed: 'Innløst',
});

/**
 * @typedef {Object} CardView  Everything the page needs to render a card.
 * @property {'denied'|'unknown'|'card'} kind
 * @property {string} [code]
 * @property {string} [type]       "60" or "90"
 * @property {string} [status]     One of STATUS
 * @property {string} [activated]  Formatted date/time, or ""
 * @property {string} [expires]    Formatted date, or ""
 * @property {boolean} [expired]
 * @property {string} [redeemed]   Formatted date/time, or ""
 * @property {string} [redeemedBy]
 * @property {string} [bookingUrl] Only for kind "denied"
 * @property {string} [message]    Optional feedback after an action
 */

/**
 * Web app entry point. Renders the card page for `?kode=<code>`.
 * @param {GoogleAppsScript.Events.DoGet} e
 * @returns {GoogleAppsScript.HTML.HtmlOutput}
 */
function doGet(e) {
  const code = String((e && e.parameter && e.parameter[CODE_PARAM]) || '').trim().toUpperCase();
  const template = HtmlService.createTemplateFromFile('Side');
  template.initialState = JSON.stringify(viewFor_(code)).replace(/</g, '\\u003c');
  return template
    .evaluate()
    .setTitle('Gavekort')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/**
 * Mark a card as sold. Called from the page via google.script.run.
 * @param {string} code
 * @returns {CardView}
 */
function activate(code) {
  return transition_(code, STATUS.notSold, (sheet, row, now, email) => {
    const expires = new Date(now);
    expires.setMonth(expires.getMonth() + validityMonths_());
    sheet.getRange(row, COL.status).setValue(STATUS.active);
    sheet.getRange(row, COL.activated).setValue(now);
    sheet.getRange(row, COL.expires).setValue(expires);
    sheet.getRange(row, COL.activatedBy).setValue(email);
  }, 'Gavekortet er aktivert.');
}

/**
 * Mark a card as used. Called from the page via google.script.run.
 * @param {string} code
 * @returns {CardView}
 */
function redeem(code) {
  return transition_(code, STATUS.active, (sheet, row, now, email) => {
    sheet.getRange(row, COL.status).setValue(STATUS.redeemed);
    sheet.getRange(row, COL.redeemed).setValue(now);
    sheet.getRange(row, COL.redeemedBy).setValue(email);
  }, 'Gavekortet er løst inn.');
}

/**
 * Create or tidy up the "Gavekort" sheet: headers, filter, validation, colours.
 * Run once from the Apps Script editor (select setupSheet → Run). Safe to re-run.
 */
function setupSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  const maxRows = sheet.getMaxRows();

  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  if (!sheet.getFilter()) {
    sheet.getRange(1, 1, maxRows, HEADERS.length).createFilter();
  }

  sheet.getRange(2, COL.code, maxRows - 1, 1).setFontFamily('Roboto Mono');
  sheet.getRange(2, COL.type, maxRows - 1, 1).setNumberFormat('@').setHorizontalAlignment('center');
  sheet.getRange(2, COL.generated, maxRows - 1, 2).setNumberFormat('yyyy-mm-dd hh:mm');
  sheet.getRange(2, COL.expires, maxRows - 1, 1).setNumberFormat('yyyy-mm-dd');
  sheet.getRange(2, COL.redeemed, maxRows - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm');

  const statusRange = sheet.getRange(2, COL.status, maxRows - 1, 1);
  statusRange.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(Object.values(STATUS), true)
      .setAllowInvalid(false)
      .build());

  const colours = [
    [STATUS.notSold, '#EEEEEE', '#555555'],
    [STATUS.active, '#D9F2E3', '#1E6B3C'],
    [STATUS.redeemed, '#F8DADA', '#8A1F1F'],
  ];
  sheet.setConditionalFormatRules(colours.map(([text, bg, fg]) =>
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(text)
      .setBackground(bg)
      .setFontColor(fg)
      .setRanges([statusRange])
      .build()));

  sheet.autoResizeColumns(1, HEADERS.length);
}

// ---------------------------------------------------------------------------
// Internals (trailing underscore = not callable from the page)
// ---------------------------------------------------------------------------

/**
 * Run a state change under a lock, after re-checking access and current status.
 * @param {string} code
 * @param {string} requiredStatus  The status the card must have for this action.
 * @param {function(GoogleAppsScript.Spreadsheet.Sheet, number, Date, string): void} apply
 * @param {string} successMessage
 * @returns {CardView}
 */
function transition_(code, requiredStatus, apply, successMessage) {
  const email = currentEmail_();
  if (!isAllowed_(email)) {
    return deniedView_();
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const found = findCard_(code);
    if (!found) {
      return { kind: 'unknown', code };
    }
    const status = String(found.sheet.getRange(found.row, COL.status).getValue());
    if (status !== requiredStatus) {
      // Someone else (or a double tap) got there first: show the real state.
      return Object.assign(cardView_(found.sheet, found.row), {
        message: `Ingen endring: kortet har status «${status}».`,
      });
    }
    apply(found.sheet, found.row, new Date(), email);
    SpreadsheetApp.flush();
    return Object.assign(cardView_(found.sheet, found.row), { message: successMessage });
  } finally {
    lock.releaseLock();
  }
}

/**
 * Build the view for a scanned code, enforcing access first.
 * @param {string} code
 * @returns {CardView}
 */
function viewFor_(code) {
  if (!isAllowed_(currentEmail_())) {
    return deniedView_();
  }
  const found = findCard_(code);
  return found ? cardView_(found.sheet, found.row) : { kind: 'unknown', code };
}

/**
 * Locate a card's row by exact code match in column A.
 * @param {string} code
 * @returns {{sheet: GoogleAppsScript.Spreadsheet.Sheet, row: number}|null}
 */
function findCard_(code) {
  if (!CODE_PATTERN.test(code)) {
    return null;
  }
  let sheet;
  try {
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  } catch (err) {
    // Runs as the scanning user: fails if the spreadsheet isn't shared with them.
    throw new Error('Kontoen din har ikke tilgang til regnearket. Be eieren dele det med deg som redigerer.');
  }
  if (!sheet) {
    throw new Error(`Fant ikke arket «${SHEET_NAME}». Kjør setupSheet først.`);
  }
  const cell = sheet
    .getRange(2, COL.code, Math.max(sheet.getLastRow() - 1, 1), 1)
    .createTextFinder(code)
    .matchEntireCell(true)
    .findNext();
  return cell ? { sheet, row: cell.getRow() } : null;
}

/**
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet
 * @param {number} row
 * @returns {CardView}
 */
function cardView_(sheet, row) {
  const values = sheet.getRange(row, 1, 1, HEADERS.length).getValues()[0];
  const at = (col) => values[col - 1];
  const expires = at(COL.expires);
  return {
    kind: 'card',
    code: String(at(COL.code)),
    type: String(at(COL.type)),
    status: String(at(COL.status)),
    activated: formatDate_(at(COL.activated), 'd. MMM yyyy HH:mm'),
    expires: formatDate_(expires, 'd. MMM yyyy'),
    expired: expires instanceof Date && expires.getTime() < Date.now(),
    redeemed: formatDate_(at(COL.redeemed), 'd. MMM yyyy HH:mm'),
    redeemedBy: String(at(COL.redeemedBy) || ''),
  };
}

/** @returns {CardView} */
function deniedView_() {
  return {
    kind: 'denied',
    bookingUrl: PropertiesService.getScriptProperties().getProperty('BOOKING_URL') || '',
  };
}

/** @returns {string} The scanning user's email, lower-cased, or "". */
function currentEmail_() {
  return (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
}

/**
 * @param {string} email
 * @returns {boolean}
 */
function isAllowed_(email) {
  const allowed = (PropertiesService.getScriptProperties().getProperty('ALLOWED_EMAILS') || '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  return email !== '' && allowed.includes(email);
}

/** @returns {number} */
function validityMonths_() {
  const raw = PropertiesService.getScriptProperties().getProperty('VALIDITY_MONTHS');
  const months = parseInt(raw || '12', 10);
  return Number.isFinite(months) && months > 0 ? months : 12;
}

/**
 * @param {*} value  A cell value; only Date instances are formatted.
 * @param {string} pattern
 * @returns {string}
 */
function formatDate_(value, pattern) {
  return value instanceof Date ? Utilities.formatDate(value, TIME_ZONE, pattern) : '';
}
