const fs = require('fs-extra');
const path = require('path');

const isDev = process.argv.includes('--dev');

async function build() {
  console.log('🔨 Building MCP Chat Extension...');
  
  // 清理输出目录
  await fs.emptyDir('dist');
  
  // 复制基本文件
  const filesToCopy = [
    'popup.html',
    'popup.js', 
    'style.css',
    'content.js',
    'background.js'
  ];
  
  for (const file of filesToCopy) {
    if (await fs.pathExists(path.join('src', file))) {
      await fs.copy(path.join('src', file), path.join('dist', file));
      console.log(`✅ Copied ${file}`);
    } else {
      console.warn(`⚠️ File not found: src/${file}`);
    }
  }
  
  // 不再复制mcp-client.js和mcp-client-simple.js，因为它们已经集成到background.js中
  
  // 复制资源文件
  if (await fs.pathExists('assets')) {
    await fs.copy('assets', 'dist');
    console.log('✅ Copied assets');
  } else {
    // 创建简单的图标文件
    console.log('⚠️ Assets folder not found, creating placeholder icons...');
    
    // 创建简单的SVG图标并转换为PNG
    const iconSvg = `
      <svg width="128" height="128" xmlns="http://www.w3.org/2000/svg">
        <rect width="128" height="128" fill="#2196F3" rx="20"/>
        <text x="64" y="80" font-family="Arial" font-size="60" fill="white" text-anchor="middle">💬</text>
      </svg>
    `;
    
    // 简单的文本文件作为占位符
    await fs.writeFile('dist/icon16.png', '');
    await fs.writeFile('dist/icon48.png', '');
    await fs.writeFile('dist/icon128.png', '');
    console.log('📝 Created placeholder icons (需要真实的PNG文件)');
  }
  
  // 创建manifest.json
  const manifest = {
    manifest_version: 3,
    name: "MCP Chat Client",
    version: "1.0.0",
    description: "Browser extension for MCP (Model Context Protocol) with DID authentication",
    permissions: [
      "storage",
      "activeTab"
    ],
    host_permissions: [
      "http://localhost:*/*",
      "https://*/"
    ],
    background: {
      service_worker: "background.js"
    },
    action: {
      default_popup: "popup.html",
      default_title: "MCP Chat",
      default_icon: {
        "16": "icon16.png",
        "48": "icon48.png",
        "128": "icon128.png"
      }
    },
    content_scripts: [
      {
        matches: ["<all_urls>"],
        js: ["content.js"],
        run_at: "document_end"
      }
    ],
    icons: {
      "16": "icon16.png",
      "48": "icon48.png",
      "128": "icon128.png"
    }
  };
  
  await fs.writeJSON('dist/manifest.json', manifest, { spaces: 2 });
  
  console.log('✅ Build completed! Extension ready in ./dist/');
  console.log('📁 Load the ./dist/ folder in Edge Extensions (Developer mode)');
  
  // 验证文件
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
  
  const output = fs.createWriteStream('mcp-chat-extension.zip');
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
  
  await fs.writeFile('scripts/package.js', packageScript);
}

build()
  .then(() => createPackageScript())
  .catch(console.error);