# 起 ERP 本地开发环境：后端 9200（后台，日志写 logs/） + 前端 5175（前台，热更新）
#
# 用法： powershell -ExecutionPolicy Bypass -File D:\erp\scripts\dev.ps1
#        只起后端： 加 -ApiOnly
#
# 端口写死与 web/vite.config.ts 的代理目标保持一致；要改端口两处一起改。

param(
    [switch]$ApiOnly
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$apiPort = 9200
$webPort = 5175
Set-Location $root

$logDir = Join-Path $root 'logs'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$apiOut = Join-Path $logDir 'api.out.log'
$apiErr = Join-Path $logDir 'api.err.log'

if ($ApiOnly) {
    Write-Host ('启动 ERP API: http://127.0.0.1:{0}' -f $apiPort)
    python -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port $apiPort
    exit $LASTEXITCODE
}

$webDir = Join-Path $root 'web'
if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
    Write-Host 'web/node_modules 不存在，先安装前端依赖 ...'
    Push-Location $webDir
    try { npm install } finally { Pop-Location }
}

$apiArgs = @(
    '-X', 'utf8', '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', [string]$apiPort
)
$api = Start-Process -FilePath 'python' -ArgumentList $apiArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr

Write-Host ('ERP API 已后台启动 pid={0}，日志: {1}' -f $api.Id, $apiOut)
Write-Host ('健康检查: http://127.0.0.1:{0}/health' -f $apiPort)
Write-Host ('ERP 界面: http://127.0.0.1:{0}（Ctrl+C 结束，后端会一起停）' -f $webPort)

try {
    Push-Location $webDir
    npm run dev
}
finally {
    Pop-Location
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force
        Write-Host 'ERP API 已停止'
    }
}