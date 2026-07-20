#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import sharp from 'sharp';

const repoRoot = process.cwd();
const heroDir = path.join(repoRoot, 'public', 'hero');
const defaultReportRoot = path.resolve(
  repoRoot,
  '..',
  '..',
  'Projeto Cafezinho Agentes',
  'Backups',
  'sprint_astro_riocarta'
);

const imageExts = new Set(['.jpg', '.jpeg', '.png', '.webp', '.avif']);

function parseArgs(argv) {
  const args = {
    apply: false,
    maxWidth: 1600,
    jpegQuality: 80,
    webpQuality: 75,
    avifQuality: 55,
    minBytes: 200 * 1024,
    minSavingsPercent: 5,
    reportRoot: defaultReportRoot,
    limit: 0,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === '--apply') args.apply = true;
    else if (arg === '--dry-run') args.apply = false;
    else if (arg === '--max-width') {
      args.maxWidth = Number(next);
      i += 1;
    } else if (arg === '--jpeg-quality') {
      args.jpegQuality = Number(next);
      i += 1;
    } else if (arg === '--webp-quality') {
      args.webpQuality = Number(next);
      i += 1;
    } else if (arg === '--avif-quality') {
      args.avifQuality = Number(next);
      i += 1;
    } else if (arg === '--min-bytes') {
      args.minBytes = Number(next);
      i += 1;
    } else if (arg === '--min-savings-percent') {
      args.minSavingsPercent = Number(next);
      i += 1;
    } else if (arg === '--report-root') {
      args.reportRoot = path.resolve(next);
      i += 1;
    } else if (arg === '--limit') {
      args.limit = Number(next);
      i += 1;
    } else if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Argumento desconhecido: ${arg}`);
    }
  }

  for (const key of ['maxWidth', 'jpegQuality', 'webpQuality', 'avifQuality', 'minBytes', 'minSavingsPercent']) {
    if (!Number.isFinite(args[key]) || args[key] < 0) {
      throw new Error(`Valor invalido para ${key}: ${args[key]}`);
    }
  }

  return args;
}

function printHelp() {
  console.log(`
Uso:
  node scripts/comprimir_hero.mjs --dry-run
  node scripts/comprimir_hero.mjs --apply

Opcoes:
  --max-width N                 Largura maxima em px. Padrao: 1600
  --jpeg-quality N              Qualidade JPEG. Padrao: 80
  --webp-quality N              Qualidade WebP. Padrao: 75
  --avif-quality N              Qualidade AVIF. Padrao: 55
  --min-bytes N                 Pula arquivos menores que N bytes se ja estiverem abaixo do max-width. Padrao: 204800
  --min-savings-percent N       So substitui se economizar ao menos N%. Padrao: 5
  --report-root PATH            Pasta raiz dos relatorios/backups
  --limit N                     Processa somente N arquivos, para smoke test
`);
}

function timestamp() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    '_',
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join('');
}

function formatBytes(bytes) {
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
}

async function listImages() {
  const entries = await fs.readdir(heroDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && imageExts.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => path.join(heroDir, entry.name))
    .sort((a, b) => a.localeCompare(b));
}

async function sha256(filePath) {
  const buffer = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

async function optimizeToBuffer(filePath, metadata, args) {
  const ext = path.extname(filePath).toLowerCase();
  let image = sharp(filePath, { animated: false, failOn: 'none' }).rotate();

  if (metadata.width && metadata.width > args.maxWidth) {
    image = image.resize({ width: args.maxWidth, withoutEnlargement: true });
  }

  if (ext === '.jpg' || ext === '.jpeg') {
    image = image.jpeg({ quality: args.jpegQuality, mozjpeg: true });
  } else if (ext === '.png') {
    image = image.png({
      compressionLevel: 9,
      adaptiveFiltering: true,
      palette: true,
    });
  } else if (ext === '.webp') {
    image = image.webp({ quality: args.webpQuality, effort: 4 });
  } else if (ext === '.avif') {
    image = image.avif({ quality: args.avifQuality, effort: 4 });
  }

  return image.toBuffer();
}

function shouldSkipBySize(stats, metadata, args) {
  return stats.size < args.minBytes && (!metadata.width || metadata.width <= args.maxWidth);
}

async function processImage(filePath, args) {
  const relativePath = path.relative(repoRoot, filePath);
  const stats = await fs.stat(filePath);
  const originalSize = stats.size;

  let metadata;
  try {
    metadata = await sharp(filePath, { failOn: 'none' }).metadata();
  } catch (error) {
    return {
      file: relativePath,
      status: 'erro_metadata',
      originalSize,
      optimizedSize: originalSize,
      savings: 0,
      message: error.message,
    };
  }

  if (shouldSkipBySize(stats, metadata, args)) {
    return {
      file: relativePath,
      status: 'skip_pequeno',
      originalSize,
      optimizedSize: originalSize,
      savings: 0,
      width: metadata.width ?? null,
      height: metadata.height ?? null,
    };
  }

  let optimized;
  try {
    optimized = await optimizeToBuffer(filePath, metadata, args);
  } catch (error) {
    return {
      file: relativePath,
      status: 'erro_otimizacao',
      originalSize,
      optimizedSize: originalSize,
      savings: 0,
      width: metadata.width ?? null,
      height: metadata.height ?? null,
      message: error.message,
    };
  }

  const optimizedSize = optimized.byteLength;
  const savings = originalSize - optimizedSize;
  const savingsPercent = originalSize > 0 ? (savings / originalSize) * 100 : 0;

  if (savings <= 0 || savingsPercent < args.minSavingsPercent) {
    return {
      file: relativePath,
      status: 'skip_sem_ganho',
      originalSize,
      optimizedSize,
      savings: Math.max(0, savings),
      savingsPercent,
      width: metadata.width ?? null,
      height: metadata.height ?? null,
    };
  }

  if (args.apply) {
    const tmpPath = `${filePath}.codex-opt.tmp`;
    await fs.writeFile(tmpPath, optimized);
    await fs.rename(tmpPath, filePath);
  }

  return {
    file: relativePath,
    status: args.apply ? 'otimizado' : 'otimizaria',
    originalSize,
    optimizedSize,
    savings,
    savingsPercent,
    width: metadata.width ?? null,
    height: metadata.height ?? null,
  };
}

function summarize(results, duplicateGroups) {
  const totals = {
    files: results.length,
    originalBytes: 0,
    projectedBytes: 0,
    savingsBytes: 0,
    changedFiles: 0,
    duplicateGroups: duplicateGroups.length,
    duplicateFiles: duplicateGroups.reduce((sum, group) => sum + group.files.length, 0),
    byStatus: {},
  };

  for (const result of results) {
    totals.originalBytes += result.originalSize ?? 0;
    totals.projectedBytes += result.optimizedSize ?? result.originalSize ?? 0;
    totals.savingsBytes += result.savings ?? 0;
    if (result.status === 'otimizado' || result.status === 'otimizaria') {
      totals.changedFiles += 1;
    }
    totals.byStatus[result.status] = (totals.byStatus[result.status] ?? 0) + 1;
  }

  totals.savingsPercent = totals.originalBytes > 0 ? (totals.savingsBytes / totals.originalBytes) * 100 : 0;
  return totals;
}

async function findDuplicates(files) {
  const groups = new Map();
  for (const file of files) {
    const hash = await sha256(file);
    if (!groups.has(hash)) groups.set(hash, []);
    groups.get(hash).push(path.relative(repoRoot, file));
  }

  return [...groups.entries()]
    .filter(([, filesInGroup]) => filesInGroup.length > 1)
    .map(([hash, filesInGroup]) => ({ hash, files: filesInGroup }));
}

function renderReport({ args, totals, results, duplicateGroups, startedAt, finishedAt }) {
  const changed = results
    .filter((result) => result.status === 'otimizado' || result.status === 'otimizaria')
    .sort((a, b) => b.savings - a.savings)
    .slice(0, 120);

  const failures = results.filter((result) => result.status.startsWith('erro_'));
  const duplicateSample = duplicateGroups.slice(0, 30);

  const lines = [];
  lines.push(`# Relatorio H6.0 - public/hero`);
  lines.push('');
  lines.push(`- Modo: ${args.apply ? 'apply' : 'dry-run'}`);
  lines.push(`- Inicio: ${startedAt.toISOString()}`);
  lines.push(`- Fim: ${finishedAt.toISOString()}`);
  lines.push(`- max-width: ${args.maxWidth}px`);
  lines.push(`- JPEG quality: ${args.jpegQuality}`);
  lines.push(`- WebP quality: ${args.webpQuality}`);
  lines.push(`- AVIF quality: ${args.avifQuality}`);
  lines.push(`- Minimo de economia para troca: ${args.minSavingsPercent}%`);
  lines.push('');
  lines.push(`## Sumario`);
  lines.push('');
  lines.push(`- Arquivos analisados: ${totals.files}`);
  lines.push(`- Tamanho original: ${formatBytes(totals.originalBytes)}`);
  lines.push(`- Tamanho ${args.apply ? 'final' : 'estimado'}: ${formatBytes(totals.projectedBytes)}`);
  lines.push(`- Economia ${args.apply ? 'obtida' : 'estimada'}: ${formatBytes(totals.savingsBytes)} (${totals.savingsPercent.toFixed(2)}%)`);
  lines.push(`- Arquivos ${args.apply ? 'otimizados' : 'que seriam otimizados'}: ${totals.changedFiles}`);
  lines.push(`- Grupos de duplicatas exatas detectados: ${totals.duplicateGroups}`);
  lines.push(`- Arquivos envolvidos em duplicatas exatas: ${totals.duplicateFiles}`);
  lines.push('');
  lines.push(`## Status`);
  lines.push('');
  for (const [status, count] of Object.entries(totals.byStatus).sort()) {
    lines.push(`- ${status}: ${count}`);
  }
  lines.push('');
  lines.push(`## Maiores economias`);
  lines.push('');
  lines.push(`| Arquivo | Antes | Depois | Economia |`);
  lines.push(`|---|---:|---:|---:|`);
  for (const result of changed) {
    lines.push(
      `| \`${result.file}\` | ${formatBytes(result.originalSize)} | ${formatBytes(result.optimizedSize)} | ${formatBytes(result.savings)} (${result.savingsPercent.toFixed(2)}%) |`
    );
  }
  lines.push('');

  if (failures.length > 0) {
    lines.push(`## Falhas`);
    lines.push('');
    for (const failure of failures) {
      lines.push(`- \`${failure.file}\`: ${failure.status} - ${failure.message ?? 'sem mensagem'}`);
    }
    lines.push('');
  }

  if (duplicateSample.length > 0) {
    lines.push(`## Amostra de duplicatas exatas`);
    lines.push('');
    for (const group of duplicateSample) {
      lines.push(`- ${group.hash.slice(0, 12)}: ${group.files.map((file) => `\`${file}\``).join(', ')}`);
    }
    lines.push('');
  }

  return `${lines.join('\n')}\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const startedAt = new Date();
  const runId = `${timestamp()}_${args.apply ? 'apply' : 'dry_run'}`;
  const reportDir = path.join(args.reportRoot, runId);
  await fs.mkdir(reportDir, { recursive: true });

  let files = await listImages();
  if (args.limit > 0) {
    files = files.slice(0, args.limit);
  }

  const results = [];
  let index = 0;
  for (const file of files) {
    index += 1;
    const result = await processImage(file, args);
    results.push(result);
    if (index % 100 === 0 || index === files.length) {
      process.stdout.write(`\rProcessados ${index}/${files.length}`);
    }
  }
  process.stdout.write('\n');

  const duplicateGroups = await findDuplicates(files);
  const finishedAt = new Date();
  const totals = summarize(results, duplicateGroups);
  const payload = { args, totals, results, duplicateGroups, startedAt, finishedAt };
  const report = renderReport(payload);

  await fs.writeFile(path.join(reportDir, 'relatorio.md'), report, 'utf8');
  await fs.writeFile(path.join(reportDir, 'relatorio.json'), JSON.stringify(payload, null, 2), 'utf8');

  console.log(`Relatorio: ${path.join(reportDir, 'relatorio.md')}`);
  console.log(`Arquivos analisados: ${totals.files}`);
  console.log(`Economia ${args.apply ? 'obtida' : 'estimada'}: ${formatBytes(totals.savingsBytes)} (${totals.savingsPercent.toFixed(2)}%)`);
  console.log(`Arquivos ${args.apply ? 'otimizados' : 'que seriam otimizados'}: ${totals.changedFiles}`);
  console.log(`Duplicatas exatas: ${totals.duplicateGroups} grupos / ${totals.duplicateFiles} arquivos`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
