$project = "project-c706c576-2724-497b-86f"
gcloud.cmd run deploy predictive-maintenance-copilot `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --max-instances 3 `
  --timeout 60 `
  --env-vars-file env.yaml `
  --project $project