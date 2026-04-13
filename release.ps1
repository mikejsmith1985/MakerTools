<#
.SYNOPSIS
    MakerTools full release pipeline — use this instead of the Forge release card.

.DESCRIPTION
    Handles every step in one shot so releases never partially fail:
      1. Clears stale GH_TOKEN (the cause of repeated 401 failures)
      2. Verifies gh CLI is authenticated before touching anything
      3. Commits staged changes, pushes the feature branch, merges to main
      4. Re-creates the version tag cleanly
      5. Creates the GitHub release
      6. Zips PathMaker, TextureForge, MisterWizard, and WiringWizard
      7. Builds WiringWizard standalone exe via PyInstaller
      8. Uploads the zip + exe assets to the release
      9. Cleans up temp files and returns to the feature branch

.PARAMETER Version
    Release version tag in the form vX.Y.Z  (e.g. v1.0.17)

.EXAMPLE
    .\release.ps1 v1.0.17
#>
param(
    [Parameter(Mandatory, HelpMessage = "Version tag — e.g. v1.0.17")]
    [ValidatePattern('^v\d+\.\d+\.\d+$')]
    [string]$Version
)

Set-StrictMode -Version Latest

# ── Step 1: Kill the stale GH_TOKEN that Forge Terminal injects into every PTY ──
# fterm.exe spawns pwsh with -NoProfile so profiles never run; the token lives
# in fterm's own process env and is inherited by every child shell.  Removing it
# here forces gh to fall back to keyring auth, which is always valid.
Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue

# ── Step 2: Verify gh is authenticated before doing any git work ─────────────
Write-Host "`n[1/7] Checking gh auth..." -ForegroundColor Cyan
$authOutput = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $authOutput -ForegroundColor Red
    Write-Error "gh CLI is not authenticated. Run:  gh auth login"
    exit 1
}
Write-Host "      ✅  Authenticated." -ForegroundColor Green

# ── Step 3: Git — commit, push feature branch, fast-forward merge to main ────
Write-Host "`n[2/7] Publishing branch and merging to main..." -ForegroundColor Cyan

$featureBranch = git branch --show-current
git add -A
git commit -m "Release $Version" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" --allow-empty
if ($LASTEXITCODE -ne 0) { Write-Error "git commit failed"; exit 1 }

git push origin $featureBranch
if ($LASTEXITCODE -ne 0) { Write-Error "git push feature branch failed"; exit 1 }

git checkout main
git pull origin main

git merge $featureBranch --no-edit
if ($LASTEXITCODE -ne 0) { Write-Error "git merge failed — resolve conflicts first"; exit 1 }

git push origin main
if ($LASTEXITCODE -ne 0) { Write-Error "git push main failed"; exit 1 }

# Re-create the tag cleanly (delete remote + local first so re-runs are safe)
git push origin ":refs/tags/$Version" 2>$null
git tag -d $Version 2>$null
git tag $Version
git push origin $Version
if ($LASTEXITCODE -ne 0) { Write-Error "git push tag failed"; exit 1 }

Write-Host "      ✅  Tag $Version pushed." -ForegroundColor Green

# ── Step 4: Create the GitHub release ────────────────────────────────────────
Write-Host "`n[3/7] Creating GitHub release..." -ForegroundColor Cyan
gh release delete $Version --yes 2>$null

gh release create $Version `
    --title "Release $Version" `
    --notes  "Release $Version" `
    --latest
if ($LASTEXITCODE -ne 0) { Write-Error "gh release create failed"; exit 1 }

Write-Host "      ✅  Release created." -ForegroundColor Green

# ── Step 5: Build zip assets ──────────────────────────────────────────────────
# Uses robocopy to stage a clean copy (no __pycache__, no credentials, no dev
# files) and then .NET ZipFile for reliable zip creation.  Compress-Archive is
# NOT used because it includes long __pycache__ paths that break Windows Explorer
# extraction and includes data/user_settings.json which may contain credentials.
Write-Host "`n[4/7] Building zip assets..." -ForegroundColor Cyan

$repoRoot   = if ($PSScriptRoot) { $PSScriptRoot } else { $PWD.Path }
$stagingDir = Join-Path $env:TEMP "MakerTools-release-$Version"
Remove-Item $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item    $stagingDir -ItemType Directory | Out-Null

Add-Type -AssemblyName System.IO.Compression.FileSystem

$zipPaths = @()
foreach ($toolName in @("PathMaker", "TextureForge", "MisterWizard", "WiringWizard")) {
    $toolSource = Join-Path $repoRoot $toolName
    $toolStage  = Join-Path $stagingDir $toolName   # folder is named $toolName so zip root is $toolName/
    $zipDest    = Join-Path $stagingDir "$toolName-$Version.zip"

    if (-not (Test-Path $toolSource)) {
        Write-Warning "Skipping $toolName — folder not found at $toolSource"
        continue
    }

    # Stage a clean copy: exclude compiled bytecode, dev/test dirs, runtime data,
    # and any credential files that should never ship in a distribution zip.
    New-Item $toolStage -ItemType Directory | Out-Null
    robocopy $toolSource $toolStage /E `
        /XD "__pycache__" "tests" ".git" `
        /XF "*.pyc" "*.pyo" "*.pyd" ".gitkeep" "user_settings.json" `
        /NFL /NDL /NJH /NJS | Out-Null

    # robocopy exit codes 0-7 are informational (0=nothing to copy, 1=ok, etc.)
    # 8+ means a real error.
    if ($LASTEXITCODE -ge 8) {
        Write-Error "robocopy failed for $toolName (exit $LASTEXITCODE)"
        exit 1
    }

    # Create zip using .NET ZipFile — more reliable than Compress-Archive.
    # $true = includeBaseDirectory so the zip contains $toolName/ at its root.
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $toolStage,
        $zipDest,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true
    )

    # Sanity-check: refuse to upload a zip that is suspiciously small.
    $zipSizeBytes = (Get-Item $zipDest).Length
    $minAcceptableBytes = 10240  # 10 KB — any real tool zip will be larger
    if ($zipSizeBytes -lt $minAcceptableBytes) {
        Write-Error "$toolName-$Version.zip is only $zipSizeBytes bytes — aborting before upload"
        exit 1
    }

    $sizeKb = [math]::Round($zipSizeBytes / 1KB, 1)
    Write-Host "      $toolName-$Version.zip  ($sizeKb KB)" -ForegroundColor Green
    $zipPaths += $zipDest
}

# ── Step 6: Build WiringWizard standalone exe ─────────────────────────────────
# PyInstaller bundles WiringWizard into a single .exe so end-users don't need
# Python installed. The exe is mandatory for release and is uploaded as a
# dedicated asset alongside the zip archives.
Write-Host "`n[5/7] Building WiringWizard standalone exe..." -ForegroundColor Cyan

$wiringWizardSource = Join-Path $repoRoot "WiringWizard"
$wiringWizardEntry  = Join-Path $wiringWizardSource "WiringWizard.py"
$exeBuildDir        = Join-Path $stagingDir "exe-build"
$exeDistDir         = Join-Path $exeBuildDir "dist"
$exeAssetName       = "WiringWizard-$Version.exe"
$exeAssetPath       = Join-Path $stagingDir $exeAssetName

$uploadPaths = @() + $zipPaths   # start with zips, may append exe below

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    Write-Error "python is required to build WiringWizard.exe"
    exit 1
}

& $pythonCommand.Source -m PyInstaller --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Installing PyInstaller..." -ForegroundColor Yellow
    & $pythonCommand.Source -m pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install PyInstaller."
        exit 1
    }
}

# --onefile    : single exe
# --windowed   : no console window (Tkinter GUI app)
# --name       : output binary name
# --distpath   : write exe here
# --workpath / --specpath : keep build artefacts in staging dir
& $pythonCommand.Source -m PyInstaller --onefile --windowed `
    --name "WiringWizard" `
    --distpath $exeDistDir `
    --workpath (Join-Path $exeBuildDir "build") `
    --specpath $exeBuildDir `
    $wiringWizardEntry 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed (exit $LASTEXITCODE)."
    exit 1
}

$builtExe = Join-Path $exeDistDir "WiringWizard.exe"
if (-not (Test-Path $builtExe)) {
    Write-Error "PyInstaller completed but expected exe was not found at $builtExe"
    exit 1
}

Copy-Item $builtExe $exeAssetPath -Force
$exeSizeKb = [math]::Round((Get-Item $exeAssetPath).Length / 1KB, 1)
Write-Host "      $exeAssetName  ($exeSizeKb KB)" -ForegroundColor Green
$uploadPaths += $exeAssetPath

# ── Step 7: Upload assets ─────────────────────────────────────────────────────
Write-Host "`n[6/7] Uploading assets to GitHub..." -ForegroundColor Cyan
gh release upload $Version @uploadPaths --clobber
if ($LASTEXITCODE -ne 0) { Write-Error "gh release upload failed"; exit 1 }

Write-Host "      ✅  $(($uploadPaths).Count) assets uploaded." -ForegroundColor Green

# ── Step 8: Clean up and return to feature branch ────────────────────────────
Write-Host "`n[7/7] Cleaning up..." -ForegroundColor Cyan
Remove-Item $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
git checkout $featureBranch

Write-Host "`n🚀  Release $Version is live:" -ForegroundColor Green
Write-Host "    https://github.com/mikejsmith1985/MakerTools/releases/tag/$Version`n" -ForegroundColor Cyan
