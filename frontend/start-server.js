#!/usr/bin/env node

/**
 * Script de démarrage personnalisé pour garantir que le serveur
 * Next.js écoute sur 0.0.0.0 (toutes les interfaces réseau)
 * pour être accessible depuis Railway healthcheck
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const port = process.env.PORT || 3000;
const hostname = '0.0.0.0'; // Force 0.0.0.0 pour être accessible depuis Railway

// Chemin vers le serveur standalone
const serverPath = path.join(__dirname, '.next', 'standalone', 'server.js');

// Vérifier que le fichier existe
if (!fs.existsSync(serverPath)) {
  console.error(`ERROR: Server file not found at ${serverPath}`);
  console.error('Make sure you have run "npm run build" first');
  process.exit(1);
}

console.log(`🚀 Starting Next.js server...`);
console.log(`   Hostname: ${hostname}`);
console.log(`   Port: ${port}`);
console.log(`   Server path: ${serverPath}`);

// Définir les variables d'environnement pour le processus enfant
const env = {
  ...process.env,
  HOSTNAME: hostname,
  PORT: String(port),
  // Next.js utilise NODE_ENV pour déterminer le mode
  NODE_ENV: process.env.NODE_ENV || 'production',
};

// Lancer le serveur standalone
const server = spawn('node', [serverPath], {
  env,
  stdio: 'inherit',
  cwd: __dirname,
});

server.on('error', (error) => {
  console.error('❌ Failed to start server:', error);
  process.exit(1);
});

server.on('exit', (code, signal) => {
  if (code !== null) {
    console.log(`⚠️  Server exited with code ${code}`);
  } else {
    console.log(`⚠️  Server exited with signal ${signal}`);
  }
  process.exit(code || 1);
});

// Gérer les signaux de terminaison
process.on('SIGTERM', () => {
  console.log('🛑 Received SIGTERM, shutting down gracefully');
  server.kill('SIGTERM');
});

process.on('SIGINT', () => {
  console.log('🛑 Received SIGINT, shutting down gracefully');
  server.kill('SIGINT');
});
