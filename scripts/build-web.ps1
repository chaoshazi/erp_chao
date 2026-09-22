# 构建 ERP 前端到 web/dist（供 FastAPI 直接托管，或给 docker compose 挂载）
#
# 用法： powershell -ExecutionPolicy Bypass -File D:\erp\scripts\build-web.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $root 'web'
Set-Location $webDir

if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
    Write-Host '安装前端依赖 ...'
    npm install
}

Write-Host '类型检查 + 构建（npm run build 内部已经包含 tsc --noEmit）...'
npm run build

$dist = Join-Path $webDir 'dist'
$index = Join-Path $dist 'index.html'
if (-not (Test-Path $index)) {
    throw ('构建产物缺失: ' + $index)
}

Write-Host ('构建完成: ' + $dist)
Write-Host '后端托管地址: http://127.0.0.1:9200'