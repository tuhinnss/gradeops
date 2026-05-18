# GRADEOPS API testing examples (PowerShell)
$Base = "http://localhost:8000/api/v1"

Write-Host "=== Health ==="
Invoke-RestMethod -Uri "http://localhost:8000/health"

Write-Host "=== Upload rubric ==="
$rubric = Invoke-RestMethod -Method Post -Uri "$Base/upload/rubric" -Form @{
    file = Get-Item -Path "samples/example_rubric.json"
    name = "Physics Midterm"
}
$rubric | ConvertTo-Json

# $rubricId = $rubric.id

Write-Host "=== Upload answer sheet (uncomment and set path) ==="
# $submission = Invoke-RestMethod -Method Post -Uri "$Base/upload/answer-sheet" -Form @{
#     file = Get-Item -Path "path\to\student_answers.pdf"
#     student_id = "STU001"
#     rubric_id = $rubricId
# }

Write-Host "=== Evaluate (uncomment) ==="
# $body = @{ submission_id = $submission.id; rubric_id = $rubricId } | ConvertTo-Json
# Invoke-RestMethod -Method Post -Uri "$Base/evaluate/run" -Body $body -ContentType "application/json"
