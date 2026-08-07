/**
 * scraper.js — Fetches transactions from Israeli banks using israeli-bank-scrapers.
 * Automatically enters credentials. OTP is entered manually in the browser window.
 *
 * Usage:
 *   node scraper.js                     # auto billing period, all banks
 *   node scraper.js --month apr_26      # specific month
 *   node scraper.js --banks hapoalim,cal
 *   node scraper.js --no-launch         # spawned from Flask (writes status files)
 */

'use strict';

const { createScraper, CompanyTypes } = require('israeli-bank-scrapers');
const fs   = require('fs');
const path = require('path');

const BASE_DIR   = __dirname;
const INPUT_DIR  = path.join(BASE_DIR, 'inputs');
const STATUS_FILE  = path.join(BASE_DIR, '_fetch_status.json');
const CONTINUE_FILE = path.join(BASE_DIR, '_fetch_continue');
const CREDS_FILE  = path.join(BASE_DIR, 'credentials_bank.json');

if (!fs.existsSync(INPUT_DIR)) fs.mkdirSync(INPUT_DIR);

// ── CLI args ──────────────────────────────────────────────────────────────────
const args      = process.argv.slice(2);
const NO_LAUNCH = args.includes('--no-launch');
const monthArg  = args.includes('--month') ? args[args.indexOf('--month') + 1] : null;
const banksArg  = args.includes('--banks') ? args[args.indexOf('--banks') + 1] : 'hapoalim,cal,max';
const BANKS     = banksArg.split(',').map(b => b.trim().toLowerCase());

// ── Status helpers ────────────────────────────────────────────────────────────
function writeStatus(status, bank, message, done = false) {
  if (!NO_LAUNCH) return;
  fs.writeFileSync(STATUS_FILE,
    JSON.stringify({ status, bank, message, done }, null, 0), 'utf8');
}

// ── Billing period helpers ────────────────────────────────────────────────────
const MONTHS = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];

function getCardPeriod(override) {
  let m, y;
  if (override) {
    const parts = override.toLowerCase().split('_');
    m = MONTHS.indexOf(parts[0]);
    y = 2000 + parseInt(parts[1], 10);
  } else {
    const today = new Date();
    if (today.getDate() >= 11) {
      m = today.getMonth();
      y = today.getFullYear();
    } else {
      m = today.getMonth() - 1;
      if (m < 0) { m = 11; y = today.getFullYear() - 1; }
      else        { y = today.getFullYear(); }
    }
  }
  const suffix = `${MONTHS[m]}_${String(y).slice(2)}`;
  return { start: new Date(y, m, 11), suffix };
}

function getPoalimPeriod(override) {
  const { suffix } = getCardPeriod(override);
  const parts = suffix.split('_');
  const m = MONTHS.indexOf(parts[0]);
  const y = 2000 + parseInt(parts[1], 10);
  return { start: new Date(y, m, 1), suffix };
}

// ── Save output ───────────────────────────────────────────────────────────────
function saveTxns(bankKey, txns, suffix) {
  const fname = `scraped_${bankKey}_${suffix}.json`;
  const fpath = path.join(INPUT_DIR, fname);
  fs.writeFileSync(fpath, JSON.stringify(txns, null, 2), 'utf8');
  console.log(`  Saved ${txns.length} transactions -> inputs/${fname}`);
}

// ── Scrape one bank ───────────────────────────────────────────────────────────
async function scrapeBank(companyId, credentials, startDate, bankLabel, bankKey, suffix) {
  writeStatus('running', bankLabel, `מסרק ${bankLabel}... (הזן OTP בדפדפן אם נדרש)`);
  console.log(`\n── ${bankLabel} ──`);

  const scraper = createScraper({
    companyId,
    startDate,
    showBrowser: true,   // keep browser visible so user can enter OTP
    verbose: false,
  });

  const result = await scraper.scrape(credentials);

  if (!result.success) {
    const msg = `${result.errorType}: ${result.errorMessage || ''}`;
    writeStatus('error', bankLabel, `שגיאה ב-${bankLabel}: ${msg}`);
    console.error(`  Error: ${msg}`);
    return false;
  }

  const allTxns = result.accounts.flatMap(acc => acc.txns);
  saveTxns(bankKey, allTxns, suffix);
  writeStatus('running', bankLabel, `${bankLabel} הושלם ✓ (${allTxns.length} עסקאות)`);
  return true;
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  if (!fs.existsSync(CREDS_FILE)) {
    const msg = 'חסר קובץ credentials_bank.json — הרץ: node setup_bank_credentials.js';
    writeStatus('error', '', msg);
    console.error(msg);
    process.exit(1);
  }

  const creds = JSON.parse(fs.readFileSync(CREDS_FILE, 'utf8'));

  const { start: poalimStart, suffix } = getPoalimPeriod(monthArg);
  const { start: cardStart }           = getCardPeriod(monthArg);

  console.log(`Poalim: from ${poalimStart.toLocaleDateString('he-IL')} (1st of month)`);
  console.log(`Cards:  from ${cardStart.toLocaleDateString('he-IL')} (11th of month)`);
  console.log(`Suffix: ${suffix}  |  Banks: ${BANKS.join(', ')}\n`);

  writeStatus('running', '', 'מאתחל...');

  if (BANKS.includes('hapoalim') && creds.hapoalim) {
    await scrapeBank(
      CompanyTypes.hapoalim, creds.hapoalim,
      poalimStart, 'פועלים', 'hapoalim', suffix
    );
  }

  if (BANKS.includes('cal') && creds.cal) {
    await scrapeBank(
      CompanyTypes.visaCal, creds.cal,
      cardStart, 'CAL', 'cal', suffix
    );
  }

  if (BANKS.includes('max') && creds.max) {
    await scrapeBank(
      CompanyTypes.max, creds.max,
      cardStart, 'Max', 'max', suffix
    );
  }

  writeStatus('done', '', 'כל הבנקים הושלמו — מרענן נתונים...', true);
  console.log('\nAll done.\n');
}

main().catch(err => {
  console.error('Fatal:', err.message);
  writeStatus('error', '', `שגיאה: ${err.message}`);
  process.exit(1);
});
