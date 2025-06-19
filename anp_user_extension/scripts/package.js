
const fs = require('fs-extra');
const archiver = require('archiver');

async function packageExtension() {
  console.log('📦 Packaging extension...');
  
  const output = fs.createWriteStream('anp-user-extension.zip');
  const archive = archiver('zip', { zlib: { level: 9 } });
  
  output.on('close', () => {
    console.log(`✅ Extension packaged: ${archive.pointer()} bytes`);
    console.log('📦 File: mcp-chat-extension.zip');
  });
  
  archive.on('error', (err) => {
    throw err;
  });
  
  archive.pipe(output);
  archive.directory('dist/', false);
  await archive.finalize();
}

packageExtension().catch(console.error);
