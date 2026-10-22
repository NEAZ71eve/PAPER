[CmdletBinding()]
param(
    [switch]$Demo,
    [switch]$NoDemo,
    [switch]$NoBrowser,
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($NoDemo) { $Demo = $false }

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $PSScriptRoot "requirements.txt"
$DefaultModel = "qwen2.5vl:3b"
$ApiPort = 0
$ServerProcess = $null

function Read-YesNo([string]$Prompt, [bool]$DefaultYes = $false) {
    if ($DefaultYes) {
        $suffix = "[Y/n]"
    } else {
        $suffix = "[y/N]"
    }
    $answer = (Read-Host "$Prompt $suffix").Trim()
    if (-not $answer) { return $DefaultYes }
    return $answer -match "^(?i:y|yes)$"
}

function Test-HttpEndpoint([string]$Url, [int]$TimeoutSeconds = 2) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        return $response
    } catch {
        return $null
    }
}

function Show-LogTail([string]$Path) {
    if (Test-Path $Path) {
        Get-Content -Path $Path -Tail 30
    }
}

function Stop-ReaderServer {
    if ($null -ne $script:ServerProcess) {
        try {
            if (-not $script:ServerProcess.HasExited) {
                Stop-Process -Id $script:ServerProcess.Id -Force -ErrorAction Stop
                Write-Host "阅读器服务已停止。" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "无法自动停止阅读器服务 PID $($script:ServerProcess.Id): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

try {
    $PythonLauncher = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not (Test-Path $Python)) {
        if ($null -eq $PythonLauncher) {
            throw "未找到 Python。请先安装 Python 3.10 或更高版本，并加入 PATH。"
        }
        Write-Host "未找到项目虚拟环境，正在创建 .venv…" -ForegroundColor Yellow
        & $PythonLauncher.Source -m venv (Join-Path $PSScriptRoot ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Python)) {
            throw "创建 .venv 失败，请检查 Python 安装。"
        }
    }

    $VersionText = & $Python --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $VersionText -notmatch "Python 3\.(\d+)") {
        throw "无法读取项目 Python 版本：$VersionText"
    }
    if ([int]$Matches[1] -lt 10) {
        throw "项目需要 Python 3.10 或更高版本，当前为 $VersionText。"
    }
    Write-Host "[ok] Python: $VersionText" -ForegroundColor Green

    $DependencyCheck = "import importlib.util,sys; modules=['fastapi','fitz','matplotlib','numpy','openai','pandas','PIL','uvicorn','multipart']; missing=[name for name in modules if importlib.util.find_spec(name) is None]; print('Missing modules: '+', '.join(missing) if missing else 'All required modules are installed'); sys.exit(bool(missing))"
    $DependencyResult = & $Python -c $DependencyCheck
    if ($LASTEXITCODE -ne 0) {
        Write-Host $DependencyResult -ForegroundColor Yellow
        if ($SkipSetup -or -not (Read-YesNo "项目依赖不完整，是否运行 pip install -r requirements.txt？" $true)) {
            throw "项目依赖不完整。可运行 .venv\Scripts\python.exe -m pip install -r requirements.txt 后重试。"
        }
        & $Python -m pip install -r $Requirements
        if ($LASTEXITCODE -ne 0) { throw "安装项目依赖失败。" }
        $DependencyResult = & $Python -c $DependencyCheck
        if ($LASTEXITCODE -ne 0) { throw "依赖安装后检查仍未通过，请检查 pip 输出。" }
    }
    Write-Host "[ok] Python 依赖完整" -ForegroundColor Green

    if (-not $env:CHART_SDK_API_PORT) { $env:CHART_SDK_API_PORT = "8000" }
    if (-not [int]::TryParse($env:CHART_SDK_API_PORT, [ref]$ApiPort) -or $ApiPort -lt 1 -or $ApiPort -gt 65535) {
        throw "CHART_SDK_API_PORT 必须是 1 到 65535 之间的端口号。"
    }
    $BaseUrl = if ($env:CHART_SDK_BASE_URL) { $env:CHART_SDK_BASE_URL.TrimEnd("/") } else { "http://localhost:11434/v1" }
    $ReaderUrl = "http://127.0.0.1:$ApiPort"

    $OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
    $IsLocalOllama = $BaseUrl -match "^https?://(localhost|127\.0\.0\.1)(:\d+)?/v1$"
    $OllamaUrl = $BaseUrl -replace "/v1$", ""
    if ($OllamaUrl -match "^http://localhost(?=:\d|$)") {
        $OllamaUrl = $OllamaUrl -replace "^http://localhost", "http://127.0.0.1"
    }
    $OllamaHealth = Test-HttpEndpoint "$OllamaUrl/api/tags"

    if ($null -eq $OllamaHealth -and $IsLocalOllama -and $null -ne $OllamaCommand) {
        Write-Host "正在启动本机 Ollama 服务…" -ForegroundColor Yellow
        $OllamaOut = Join-Path $env:TEMP "paper-reader-ollama-$PID.out.log"
        $OllamaErr = Join-Path $env:TEMP "paper-reader-ollama-$PID.err.log"
        $OllamaProcess = Start-Process -FilePath $OllamaCommand.Source -ArgumentList "serve" `
            -PassThru -WindowStyle Hidden -RedirectStandardOutput $OllamaOut -RedirectStandardError $OllamaErr
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            $OllamaHealth = Test-HttpEndpoint "$OllamaUrl/api/tags"
            if ($null -ne $OllamaHealth) { break }
            if ($OllamaProcess.HasExited) { break }
        }
    }

    $Model = $env:CHART_SDK_MODEL
    if (-not $Model) { $Model = $DefaultModel }
    if ($IsLocalOllama -and $null -ne $OllamaHealth) {
        $Models = @()
        try {
            $ModelData = $OllamaHealth.Content | ConvertFrom-Json
            $Models = @($ModelData.models | ForEach-Object { $_.name })
        } catch {
            throw "无法读取 Ollama 模型列表。请检查 $OllamaUrl/api/tags。"
        }

        if ($env:CHART_SDK_MODEL -and $Model -notin $Models) {
            Write-Host "指定模型 $Model 未安装。" -ForegroundColor Yellow
        } elseif (-not $env:CHART_SDK_MODEL -and $Model -notin $Models) {
            $PreferredModel = @("qwen2.5vl:3b", "qwen2.5vl:7b") | Where-Object { $_ -in $Models } | Select-Object -First 1
            if (-not $PreferredModel) {
                $PreferredModel = $Models | Where-Object { $_ -match "vl" } | Select-Object -First 1
            }
            if ($PreferredModel) {
                $Model = $PreferredModel
                Write-Host "默认模型未安装，改用本机已安装的视觉模型：$Model" -ForegroundColor Yellow
            }
        }

        if ($Model -notin $Models) {
            Write-Host "本机 Ollama 模型：$(if ($Models.Count) { $Models -join ', ' } else { '无' })"
            if ($SkipSetup -or -not (Read-YesNo "是否下载视觉模型 $Model？（需要网络和数 GB 磁盘空间）")) {
                throw "模型 $Model 不可用。运行 ollama pull $Model，或设置 CHART_SDK_MODEL 为已安装的视觉模型。"
            }
            if ($null -eq $OllamaCommand) {
                throw "找不到 ollama.exe，无法自动下载模型。请安装 Ollama 或手动安装模型 $Model。"
            }
            & $OllamaCommand.Source pull $Model
            if ($LASTEXITCODE -ne 0) { throw "下载模型 $Model 失败。" }
        }
        $env:CHART_SDK_MODEL = $Model
        Write-Host "[ok] Ollama 已就绪，视觉模型：$Model" -ForegroundColor Green
    } elseif ($IsLocalOllama) {
        if ($null -eq $OllamaCommand) {
            throw "无法连接本机 Ollama，且未找到 ollama.exe。请安装并启动 Ollama。"
        }
        throw "无法连接 Ollama（$OllamaUrl）。请检查 Ollama 服务，或确认端口没有被占用。"
    } else {
        if (-not $env:CHART_SDK_BASE_URL) {
            throw "CHART_SDK_BASE_URL 无效。"
        }
        Write-Host "[!] 使用自定义模型端点：$BaseUrl；请确认该端点已运行且模型 $Model 可用。" -ForegroundColor Yellow
        $env:CHART_SDK_MODEL = $Model
    }

    $ExistingReader = Test-HttpEndpoint "$ReaderUrl/"
    if ($null -ne $ExistingReader) {
        $HealthResponse = Test-HttpEndpoint "$ReaderUrl/api/health" 10
        if ($null -eq $HealthResponse) {
            throw "端口 $ApiPort 已有服务响应，但健康检查失败。请检查现有进程，或设置其他 CHART_SDK_API_PORT。"
        }
        $HealthData = $HealthResponse.Content | ConvertFrom-Json
        if (-not $HealthData.ollama -or -not $HealthData.model -or $HealthData.model_name -ne $Model) {
            throw "已运行的阅读器模型检查未通过。当前模型：$($HealthData.model_name)。请启动可用模型后重试。"
        }
        Write-Host "[ok] 复用已运行的阅读器：$ReaderUrl" -ForegroundColor Green
        if ($Demo) { $ReaderUrl += "/?demo=synthetic" }
        if (-not $NoBrowser) {
            Start-Process $ReaderUrl
            Write-Host "已请求系统默认浏览器打开阅读器。" -ForegroundColor Cyan
        }
        Write-Host "如未看到页面，请在浏览器地址栏打开：" -ForegroundColor Yellow
        Write-Host "  $ReaderUrl" -ForegroundColor White
        Write-Host "复用的服务不受本启动脚本 Ctrl+C 控制。" -ForegroundColor DarkGray
        return
    }

    $PortProbe = $null
    try {
        $PortProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $ApiPort)
        $PortProbe.Start()
        $PortProbe.Stop()
    } catch {
        throw "端口 $ApiPort 已被占用，但不是可复用的论文阅读器。请关闭占用程序或设置 CHART_SDK_API_PORT。"
    }

    $SamplePdf = Join-Path $PSScriptRoot "assets\samples\synthetic-demo.pdf"
    if ($Demo -and -not (Test-Path $SamplePdf)) {
        Write-Host "正在生成内置效果测试论文…" -ForegroundColor Yellow
        & $Python (Join-Path $PSScriptRoot "scripts\make_synthetic_sample.py")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $SamplePdf)) {
            throw "生成效果测试论文失败。"
        }
    }

    $LogDir = Join-Path $env:TEMP "paper-reader"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $StdoutLog = Join-Path $LogDir "server-$ApiPort.out.log"
    $StderrLog = Join-Path $LogDir "server-$ApiPort.err.log"
    $ServerProcess = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
        -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog

    Write-Host "正在启动论文阅读器…" -ForegroundColor Cyan
    $Ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        if ($ServerProcess.HasExited) {
            Show-LogTail $StderrLog
            throw "阅读器服务提前退出。详细日志：$StderrLog"
        }
        if ($null -ne (Test-HttpEndpoint "$ReaderUrl/")) {
            $Ready = $true
            break
        }
    }
    if (-not $Ready) {
        Show-LogTail $StderrLog
        throw "阅读器启动超时。详细日志：$StderrLog"
    }

    $HealthResponse = Test-HttpEndpoint "$ReaderUrl/api/health" 10
    if ($null -eq $HealthResponse) {
        Show-LogTail $StderrLog
        throw "阅读器网页已启动，但 Ollama 健康检查失败。详细日志：$StderrLog"
    }
    $HealthData = $HealthResponse.Content | ConvertFrom-Json
    if (-not $HealthData.ollama -or -not $HealthData.model -or $HealthData.model_name -ne $Model) {
        throw "阅读器已启动，但模型健康检查未通过。当前模型：$($HealthData.model_name)。请检查 Ollama 与 CHART_SDK_MODEL。"
    }

    if ($Demo) {
        $ReaderUrl += "/?demo=synthetic"
        Write-Host "[ok] 将自动导入合成测试论文（折线图、柱状图、热力图）" -ForegroundColor Green
    }
    if (-not $NoBrowser) {
        Start-Process $ReaderUrl
    }

    Write-Host ""
    Write-Host "  论文阅读器已就绪" -ForegroundColor Cyan
    Write-Host "  页面 : $ReaderUrl"
    Write-Host "  模型 : $env:CHART_SDK_MODEL"
    Write-Host "  日志 : $StderrLog"
    if (-not $Demo) {
        Write-Host "  导入 : $SamplePdf"
        Write-Host "  提示 : 点击「文件 → 导入论文」，选择样例 PDF 或你的论文。"
    }
    Write-Host "  按 Ctrl+C 停止阅读器服务" -ForegroundColor DarkGray
    Write-Host ""

    while (-not $ServerProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    $ServerProcess.Refresh()
    if ($ServerProcess.ExitCode -ne 0) {
        Show-LogTail $StderrLog
        throw "阅读器服务异常退出（退出代码：$($ServerProcess.ExitCode)）。"
    }
} catch {
    Write-Host "[x] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Stop-ReaderServer
}
