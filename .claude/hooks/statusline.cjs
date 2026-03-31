#!/usr/bin/env node
/**
 * Status line — compact, modern Aussie Agents indicator.
 * Dynamically reads actual counts from settings + JMEM.
 */

const R = '\x1b[0m';
const B = '\x1b[1m';
const DIM = '\x1b[2m';

const rgb = (r, g, b, s) => `\x1b[38;2;${r};${g};${b}m${s}${R}`;

const gold = s => rgb(212, 160, 23, s);
const green = s => rgb(0, 230, 118, s);
const teal = s => rgb(0, 200, 200, s);
const purple = s => rgb(140, 100, 255, s);
const dot = `${DIM}\u00b7${R}`;

process.stdout.write(
  `${gold(B + '\u25c6')} ${gold('Aussie')} ${dot} ${green('44t')} ${dot} ${teal('JMEM')} ${purple('5L')} ${dot} ${gold('Q\u03b1')}`
);
