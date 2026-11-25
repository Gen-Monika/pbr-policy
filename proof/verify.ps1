$ErrorActionPreference = 'Continue'
$leanLakeCommand = Get-Command lake -ErrorAction Stop
Push-Location -LiteralPath $PSScriptRoot
try {
    & $leanLakeCommand.Source build
    if ($LASTEXITCODE -ne 0) { throw 'Lean project build failed.' }
    & $leanLakeCommand.Source env lean 'PreconditionerProof/Audit.lean'
    if ($LASTEXITCODE -ne 0) { throw 'Axiom audit failed.' }
    Write-Host 'All formal proofs and the axiom audit passed.' -ForegroundColor Green
} finally {
    Pop-Location
}
