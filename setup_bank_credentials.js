/**
 * setup_bank_credentials.js
 * Run once to create credentials_bank.json with your bank login details.
 * Usage: node setup_bank_credentials.js
 */

'use strict';

const fs       = require('fs');
const path     = require('path');
const readline = require('readline');

const CREDS_FILE = path.join(__dirname, 'credentials_bank.json');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise(resolve => rl.question(q, resolve));

async function main() {
  console.log('\n=== Bank Credentials Setup ===');
  console.log('Credentials are saved locally to credentials_bank.json');
  console.log('This file is NOT committed to git.\n');

  const existing = fs.existsSync(CREDS_FILE)
    ? JSON.parse(fs.readFileSync(CREDS_FILE, 'utf8'))
    : {};

  // Hapoalim
  console.log('── Bank Hapoalim ──');
  console.log('(userCode = מספר משתמש באינטרנט בנקאי)');
  const hUserCode = await ask(`  userCode  [${existing.hapoalim?.userCode || ''}]: `);
  const hPassword = await ask(`  password  [${existing.hapoalim?.password ? '***' : ''}]: `);

  // CAL
  console.log('\n── Visa CAL ──');
  console.log('(username = תעודת זהות)');
  const cUser = await ask(`  username  [${existing.cal?.username || ''}]: `);
  const cPass = await ask(`  password  [${existing.cal?.password ? '***' : ''}]: `);

  // Max
  console.log('\n── Max ──');
  console.log('(username = תעודת זהות)');
  const mUser = await ask(`  username  [${existing.max?.username || ''}]: `);
  const mPass = await ask(`  password  [${existing.max?.password ? '***' : ''}]: `);

  rl.close();

  const creds = {
    hapoalim: {
      userCode: hUserCode || existing.hapoalim?.userCode || '',
      password: hPassword || existing.hapoalim?.password || '',
    },
    cal: {
      username: cUser || existing.cal?.username || '',
      password: cPass || existing.cal?.password || '',
    },
    max: {
      username: mUser || existing.max?.username || '',
      password: mPass || existing.max?.password || '',
    },
  };

  fs.writeFileSync(CREDS_FILE, JSON.stringify(creds, null, 2), 'utf8');
  console.log(`\nSaved to ${CREDS_FILE}`);
  console.log('Run: node scraper.js  to test\n');
}

main().catch(err => { console.error(err); process.exit(1); });
