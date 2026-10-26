#!/usr/bin/env node
/**
 * notify-indexnow.js — PumpChecker.co.uk
 * Notifies Bing, IndexNow, and search engines about the most important live fuel URLs.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HOST = 'pumpchecker.co.uk';
const KEY = 'd7192a54e9bc4fa58e65842c129e917d';
const KEY_LOCATION = `https://${HOST}/${KEY}.txt`;

const citiesPath = path.join(__dirname, '..', 'src', 'data', 'uk_cities.json');
const brandsPath = path.join(__dirname, '..', 'src', 'data', 'uk_brands.json');

const cities = JSON.parse(fs.readFileSync(citiesPath, 'utf8'));
const brands = JSON.parse(fs.readFileSync(brandsPath, 'utf8'));

const urlList = [
  `https://${HOST}/`,
  `https://${HOST}/fuel-prices/diesel/`,
  `https://${HOST}/fuel-prices/unleaded-e10/`,
  `https://${HOST}/fuel-prices/super-unleaded-e5/`,
  `https://${HOST}/cheapest-petrol-near-me/`,
  `https://${HOST}/supermarket-fuel/`,
];

// Add brand hubs
brands.forEach(b => {
  urlList.push(`https://${HOST}/brand/${b.slug}/`);
});

// Add top 60 major UK cities across fuel types
cities.slice(0, 60).forEach(c => {
  urlList.push(`https://${HOST}/petrol-stations/${c.slug}/`);
  urlList.push(`https://${HOST}/petrol-stations/${c.slug}/diesel/`);
  urlList.push(`https://${HOST}/petrol-stations/${c.slug}/unleaded-e10/`);
});

// Trim to top 200 URLs
const selectedUrls = urlList.slice(0, 200);

console.log(`[IndexNow] PumpChecker.co.uk — Pinging ${selectedUrls.length} priority URLs`);
console.log(`[IndexNow] First URL: ${selectedUrls[0]}`);
console.log(`[IndexNow] Last URL:  ${selectedUrls[selectedUrls.length - 1]}`);

const payload = {
  host: HOST,
  key: KEY,
  keyLocation: KEY_LOCATION,
  urlList: selectedUrls
};

async function ping(endpoint) {
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(payload)
    });
    console.log(`[IndexNow] ${endpoint} -> status ${res.status}`);
  } catch (err) {
    console.error(`[IndexNow] ${endpoint} error:`, err.message);
  }
}

async function run() {
  await ping('https://api.indexnow.org/indexnow');
  await ping('https://www.bing.com/indexnow');
  await ping('https://yandex.com/indexnow');
}

run();
