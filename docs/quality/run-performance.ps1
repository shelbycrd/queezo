param(
  [ValidateSet('live','mock')][string]$Mode = 'live',
  [string]$OutName = "performance-$Mode",
  [int]$Seed = 42,
  [ValidateSet(10,50,150)][int[]]$Sizes = @(10,50,150),
  [switch]$ColdOnly
)

$ErrorActionPreference = 'Stop'
if ($OutName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Choose a simple output name.' }
$quality = $PSScriptRoot
$repoRoot = Split-Path (Split-Path $quality)
$results = Join-Path $quality 'results'
[void](New-Item -ItemType Directory -Force -Path $results)
$resources = Join-Path $results "$OutName-host.csv"
$metadata = Join-Path $results "$OutName-hardware.json"

Push-Location $repoRoot
try {
  docker compose -p queezo-perf build --quiet backend
  if ($LASTEXITCODE -ne 0) { throw 'Benchmark image build failed.' }
  $cpuInfo = Get-CimInstance Win32_Processor | Select-Object -First 1
  $systemInfo = Get-CimInstance Win32_ComputerSystem
  $osInfo = Get-CimInstance Win32_OperatingSystem
  $dockerInfo = docker info --format '{{.ServerVersion}} / {{.KernelVersion}} / {{.NCPU}} CPUs / {{.MemTotal}} bytes'
  if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Docker.' }
  $gpuInfo = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    @(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader)
  } else { @() }
  [ordered]@{
    cpu = $cpuInfo.Name
    physical_cores = $cpuInfo.NumberOfCores
    logical_cores = $cpuInfo.NumberOfLogicalProcessors
    physical_memory_bytes = $systemInfo.TotalPhysicalMemory
    os = $osInfo.Caption
    os_build = $osInfo.BuildNumber
    docker = $dockerInfo
    gpu_nvidia = @($gpuInfo)
    host_sample_interval_ms = 500
  } | ConvertTo-Json | Set-Content -Encoding utf8 $metadata

  $sampler = Start-Job -ArgumentList $resources -ScriptBlock {
    param($sampleFile)
    $invariant = [System.Globalization.CultureInfo]::InvariantCulture
    'utc_epoch,pid,cpu_s,working_set_bytes' | Set-Content -Encoding ascii $sampleFile
    while ($true) {
      $ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
      $stamp = ($ms / 1000).ToString($invariant)
      $rows = @(
        Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue |
          Where-Object { $null -ne $_.CPU } |
          ForEach-Object { "$stamp,$($_.Id),$($_.CPU.ToString($invariant)),$($_.WorkingSet64)" }
      )
      if ($rows.Count) { Add-Content -Encoding ascii $sampleFile $rows }
      Start-Sleep -Milliseconds 500
    }
  }
  try {
    Start-Sleep -Milliseconds 500
    $flags = @()
    if ($Mode -eq 'mock') { $flags += @('--network','none') }
    $benchmarkFlags = @('--sizes') + $Sizes
    if ($ColdOnly) { $benchmarkFlags += '--cold-only' }
    docker run --rm @flags --mount "type=bind,source=$quality,target=/quality" -e PYTHONPATH=/app -e OLLAMA_BASE_URL=http://host.docker.internal:11434 -e OLLAMA_MODEL=qwen3:1.7b queezo-perf-backend python /quality/benchmark_performance.py --mode $Mode --seed $Seed --out "/quality/results/$OutName.json" @benchmarkFlags
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed. Any completed scenarios were recorded.' }
    if ($Mode -eq 'live') {
      $state = Invoke-RestMethod 'http://localhost:11434/api/ps' -TimeoutSec 5
      @($state.models | Where-Object { $_.name -eq 'qwen3:1.7b' } |
        Select-Object name,size,size_vram,context_length) |
        ConvertTo-Json -AsArray | Set-Content -Encoding utf8 (Join-Path $results "$OutName-ollama.json")
    }
    Start-Sleep -Milliseconds 550
  }
  finally {
    Stop-Job $sampler
    Remove-Job $sampler
  }
}
finally {
  Pop-Location
}
