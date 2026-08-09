param(
    [string]$Image = "bilibili-live-notification-apprise:latest",
    [string]$Output = "dist/bilibili-live-notification-apprise-amd64.tar"
)

$ErrorActionPreference = "Stop"
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) {
    $dockerCommand.Source
} else {
    Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
}
if (-not (Test-Path -LiteralPath $dockerPath)) {
    throw "未找到 docker。请安装 Docker Desktop 或在具有 Docker Engine 的构建机上运行。"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $Output))
$outputDirectory = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

& $dockerPath build --platform linux/amd64 --tag $Image $projectRoot
if ($LASTEXITCODE -ne 0) { throw "Docker 镜像构建失败。" }

& $dockerPath image inspect $Image --format '{{.Architecture}}/{{.Os}}'
if ($LASTEXITCODE -ne 0) { throw "无法检查构建后的镜像。" }

& $dockerPath save --output $outputPath $Image
if ($LASTEXITCODE -ne 0) { throw "Docker 镜像导出失败。" }

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $outputPath
Write-Host "镜像已导出：$outputPath"
Write-Host "SHA256：$($hash.Hash.ToLowerInvariant())"
