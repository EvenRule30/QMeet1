$ErrorActionPreference = 'Stop'

$checks = @(
    @{ Path = 'backend/app/focus/lifecycle.py'; Pattern = 'class NativeFocusUpdateRequest' },
    @{ Path = 'backend/app/routers/focus_lifecycle.py'; Pattern = '@router.post("/update"' },
    @{ Path = 'backend/app/routers/command.py'; Pattern = '(?:the|my|our|current|active)' },
    @{ Path = 'src/app/lib/nativeFocusLifecycle.ts'; Pattern = 'updateNativeFocusVerified' },
    @{ Path = 'src/app/lib/nativeFocusLifecycle.ts'; Pattern = '/api/focus/lifecycle/update' },
    @{ Path = 'src/app/commandHandlers/memory.ts'; Pattern = "commandMatch.command === 'update-focus-session'" }
)

$failed = $false
foreach ($check in $checks) {
    if (-not (Test-Path $check.Path)) {
        Write-Host "MISSING: $($check.Path)" -ForegroundColor Red
        $failed = $true
        continue
    }
    $match = Select-String -Path $check.Path -SimpleMatch -Pattern $check.Pattern -Quiet
    if ($match) {
        Write-Host "OK: $($check.Path) contains $($check.Pattern)" -ForegroundColor Green
    } else {
        Write-Host "MISSING MARKER: $($check.Path) -> $($check.Pattern)" -ForegroundColor Red
        $failed = $true
    }
}

if ($failed) {
    throw 'Phase 20D2A3 is not fully installed.'
}

Write-Host 'Phase 20D2A3 source installation is complete.' -ForegroundColor Green
