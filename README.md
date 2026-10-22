# AEON `api` – CI/CD and GitOps take-home

A small Python HTTP service (`app/`) delivered to **dev** and **prod** Kubernetes clusters:
Jenkins tests, builds, scans and pushes an immutable image, then updates a GitOps repo.
Argo CD reconciles the cluster. Jenkins never runs `kubectl`.

```
Dockerfile            hardened, non-root image
Jenkinsfile           test -> build -> scan -> push -> dev overlay -> (approval) -> prod PR
app/                  service + unit tests (standard library only)
gitops/base/          Deployment, Service, ServiceAccount, NetworkPolicy
gitops/overlays/dev|prod   Kustomize overlays (replicas, resources, namespace, image tag)
gitops/argocd/        AppProject + one Application per environment
```

Kustomize only (no Helm). In a real setup `gitops/` lives in its own repository; it is in
this repo for easy review.

## AI disclosure
I used an AI assistant (Claude) to help draft the files and this README. I reviewed them and
can explain every decision in the follow-up. Nothing was run against real Jenkins, registry,
AWS or Argo CD.

## Validate locally
```bash
# Application tests
cd app && python3 -m unittest -v && cd ..

# Container
docker build -t aeon-api:test .
docker run --rm -p 8080:8080 aeon-api:test &   # then: curl localhost:8080/healthz
hadolint Dockerfile                              # optional lint
trivy image aeon-api:test --severity HIGH,CRITICAL   # same scan the pipeline runs

# Kubernetes config
kustomize build gitops/overlays/dev
kustomize build gitops/overlays/prod
kustomize build gitops/overlays/prod | kubeconform -strict -summary   # schema check
kustomize build gitops/overlays/prod | kubectl apply --dry-run=client -f -   # needs a cluster context
```
Status when written: unit tests pass; both overlays build and the 9 rendered resources pass
`kubeconform -strict`. **The Dockerfile was not built** (no Docker daemon in my authoring
environment); the Jenkinsfile and Argo CD manifests were not executed.

## Assumptions
- GitHub-style Git hosting and PR workflow; Jenkins runs on Kubernetes (pod agents).
- Registry is ECR with **tag immutability enabled**; `registry.example.com` and all
  `example.com` URLs are placeholders.
- Two EKS clusters (dev, prod), each registered in one Argo CD instance; `main` of the GitOps
  repo is branch-protected (reviews required, bot may only push the dev overlay).
- The app listens on 8080 and needs no Kubernetes API access.

## Building images safely
The pipeline uses **Kaniko** in an ephemeral pod: no Docker daemon, no privileged container,
no mounted `docker.sock`. Docker-in-Docker needs privileged mode and the socket mount gives root
on the node, so both were rejected. BuildKit rootless is a good alternative and faster with
caching. Kaniko trade-offs: slower, and it executes build steps as root inside its own container,
so build agents are still isolated from the rest of the cluster (own namespace, no cloud
credentials beyond push access). The image is built with `--no-push`, scanned as a tarball, and
only pushed if the scan passes.

## Promotion: dev to production
1. Push to `main`: Jenkins runs tests, a source secret scan, builds and scans the image.
2. The image is pushed as `api:<git-sha>` (immutable in the registry).
3. Jenkins commits that tag to `gitops/overlays/dev`; Argo CD syncs dev automatically.
4. After a human approval, Jenkins opens a **pull request** changing the prod overlay to the same
   tag. Before opening it, the pipeline checks that the dev overlay on `main` carries exactly this
   build's tag (and, as pseudocode, that the dev Argo app is Synced and Healthy).
5. A reviewer merges; Argo CD syncs prod.

**Why an untested image cannot reach prod:** only the pipeline can write tags, and it writes them
only after tests and scan succeed. Prod tags are copied from dev, not typed by hand. Branch
protection and CODEOWNERS on `overlays/prod` force a review. Feature branches never push images.

## Secrets in AWS
No secrets in Git. Secrets live in **AWS Secrets Manager** (one path per environment, KMS
encrypted). **External Secrets Operator** creates the Kubernetes Secret from a reference
(`gitops/base/externalsecret.example.yaml`, deliberately not enabled). The operator and pods
authenticate with **IRSA / EKS Pod Identity**, so there are no static AWS keys. Jenkins stores the
registry and Git tokens in its credential store (or uses an IAM role), injected with
`withCredentials` and masked in logs.

## Rollback
Rollback is a Git operation: `git revert` the promotion commit (or PR) on `main`; Argo CD
returns the cluster to the previous immutable tag. For an urgent prod incident, use the Argo CD
**rollback/sync to previous revision** as a stop-gap, then commit the revert so Git stays the
source of truth (self-heal would otherwise undo a manual rollback). `maxUnavailable: 0`, readiness
probes and the PodDisruptionBudget keep a bad rollout from taking capacity away.

## Security settings in the manifests
Non-root UID 10001, `readOnlyRootFilesystem`, all capabilities dropped, no privilege escalation,
`RuntimeDefault` seccomp, no service-account token mounted, ClusterIP service on one port,
NetworkPolicy allowing ingress only to 8080, Argo CD project limited to two namespaces and a
whitelist of namespaced kinds.

## Intentionally not implemented (time limit)
Real Jenkins/Kubernetes/Argo CD test run; image signing (cosign) and SBOM; Terraform for the AWS
foundation; Ingress/ALB and TLS; HPA; egress NetworkPolicy; monitoring and alerts; Argo CD
notifications; automatic digest pinning for the base image.

## Next improvements for production
1. Sign images with cosign and verify with an admission policy (Kyverno).
2. Pin base images by digest with Renovate; generate and store SBOMs.
3. Progressive delivery (Argo Rollouts canary with automatic rollback on SLO breach).
4. Dashboards and alerts (latency, 5xx, saturation) tied to the promotion gate.
5. Terraform/Terragrunt for EKS, ECR, IAM and Argo CD bootstrap; tested cluster rebuild runbook.
6. Pod Security Admission `restricted`, egress policies, Argo CD SSO and RBAC.

## Time spent
**TODO (Nikolas): fill in your real time, e.g. "about 3.5 hours".** Do not submit this line unedited.
