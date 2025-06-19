const fs = require('fs-extra');
const path = require('path');

async function build() {
  console.log('🔨 Building ANP User Extension...');
  
  // 清理输出目录
  await fs.emptyDir('dist');
  
  // 复制基本文件
  const filesToCopy = [
    'popup.html',
    'popup.js', 
    'style.css'
  ];
  
  for (const file of filesToCopy) {
    if (await fs.pathExists(path.join('src', file))) {
      await fs.copy(path.join('src', file), path.join('dist', file));
      console.log(`✅ Copied ${file}`);
    } else {
      console.warn(`⚠️ File not found: src/${file}`);
    }
  }
  
  // 复制 manifest.json（如果你手动维护在 src），否则在此生成
  if (await fs.pathExists(path.join('src', 'manifest.json'))) {
    await fs.copy(path.join('src', 'manifest.json'), path.join('dist', 'manifest.json'));
    console.log('✅ Copied manifest.json');
  } else {
    // 自动生成 manifest.json
  const manifest = {
    manifest_version: 3,
      name: "ANP User Extension",
    version: "1.0.0",
      description: "ANP用户的Chrome 扩展，支持自定义 OpenAI 兼容 API。",
    action: {
      default_popup: "popup.html",
      default_icon: {
        "16": "icon16.png",
        "48": "icon48.png",
        "128": "icon128.png"
      }
    },
      permissions: [
        "storage"
      ],
    icons: {
      "16": "icon16.png",
      "48": "icon48.png",
      "128": "icon128.png"
    }
  };
  await fs.writeJSON('dist/manifest.json', manifest, { spaces: 2 });
    console.log('✅ Generated manifest.json');
  }
  
  // 生成或复制 icons
  if (await fs.pathExists('assets')) {
    await fs.copy('assets', 'dist');
    console.log('✅ Copied assets');
  } else {
    // 创建简单的占位符 icon
    await fs.writeFile('dist/icon16.png', '');
    await fs.writeFile('dist/icon48.png', '');
    await fs.writeFile('dist/icon128.png', '');
    console.log('📝 Created placeholder icons (请替换为真实 PNG 文件)');
  }

  console.log('✅ Build completed! Extension ready in ./dist/');
  const distFiles = await fs.readdir('dist');
  console.log('📋 Generated files:', distFiles);
}

// 创建包脚本
async function createPackageScript() {
  const packageScript = `
const fs = require('fs-extra');
const archiver = require('archiver');

async function packageExtension() {
  console.log('📦 Packaging extension...');
  
  const output = fs.createWriteStream('anp-user-extension.zip');
  const archive = archiver('zip', { zlib: { level: 9 } });
  
  output.on('close', () => {
    console.log(\`✅ Extension packaged: \${archive.pointer()} bytes\`);
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
`;
  
  await fs.ensureDir('scripts');
  await fs.writeFile('scripts/package.js', packageScript);
}

build()
  .then(() => createPackageScript())
  .catch(console.error);