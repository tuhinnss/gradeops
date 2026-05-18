#!/usr/bin/env bash
# GRADEOPS API testing examples (requires curl and running server on :8000)

BASE="http://localhost:8000/api/v1"

echo "=== Health ==="
curl -s "http://localhost:8000/health" | jq .

echo "=== Upload rubric (JSON) ==="
curl -s -X POST "$BASE/upload/rubric" \
  -F "file=@samples/example_rubric.json" \
  -F "name=Physics Midterm" | jq .

# Save rubric_id from response, then:
# RUBRIC_ID="<uuid-from-response>"

echo "=== Upload answer sheet ==="
# curl -s -X POST "$BASE/upload/answer-sheet" \
#   -F "file=@path/to/student_answers.pdf" \
#   -F "student_id=STU001" \
#   -F "rubric_id=$RUBRIC_ID" | jq .

echo "=== Run evaluation ==="
# curl -s -X POST "$BASE/evaluate/run" \
#   -H "Content-Type: application/json" \
#   -d "{\"submission_id\": \"<uuid>\", \"rubric_id\": \"$RUBRIC_ID\"}" | jq .

echo "=== Get results ==="
# curl -s "$BASE/results/<submission_id>" | jq .

echo "=== Download annotated PDF ==="
# curl -s -o annotated.pdf "$BASE/results/<submission_id>/annotated-pdf"
