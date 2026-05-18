# GRADEOPS — GitHub push helper (first push or upgrade)
# Requires Git: https://git-scm.com/download/win — then reopen PowerShell.
#
# First time:
#   .\scripts\push-to-github.ps1 -RepoUrl "https://github.com/YOUR_USER/gradeops.git"
#
# Upgrade (existing repo):
#   .\scripts\push-to-github.ps1 -RepoUrl "https://github.com/YOUR_USER/gradeops.git" -Message "Phase 2: bulk upload, auth, review, analytics"

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl,

    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed. Install from https://git-scm.com/download/win, restart PowerShell, then run this script again."
}

if (Test-Path .env) {
    Write-Host "Note: .env is gitignored (secrets stay local)." -ForegroundColor Yellow
}

if (-not (Test-Path .git)) {
    git init
    git branch -M main
    Write-Host "Initialized new git repository (branch: main)." -ForegroundColor Cyan
}

git add -A
git status -sb

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "Nothing to commit (working tree clean)." -ForegroundColor Yellow
} else {
    if (-not $Message) {
        $hasHead = git rev-parse HEAD 2>$null
        if (-not $hasHead) {
            $Message = @"
Initial commit: GRADEOPS exam grading platform.

FastAPI backend (OCR, rubric parsing, grading) and Next.js dashboard.
"@
        } else {
            $Message = @"
Upgrade GRADEOPS: Phase 2 features and evaluate-all.

Bulk/ZIP upload, batch evaluation, optional JWT auth, HITL review,
analytics, plagiarism reports, evaluate-all, Alembic scaffold, tests.
"@
        }
    }
    git commit -m $Message
    Write-Host "Committed changes." -ForegroundColor Green
}

$remote = git remote get-url origin 2>$null
if (-not $remote) {
    git remote add origin $RepoUrl
} else {
    if ($remote -ne $RepoUrl) {
        git remote set-url origin $RepoUrl
    }
}

Write-Host "Pushing to $RepoUrl ..." -ForegroundColor Cyan
git push -u origin main

Write-Host "Done. Verify on GitHub." -ForegroundColor Green
