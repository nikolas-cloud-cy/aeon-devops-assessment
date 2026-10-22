// Declarative pipeline for the `api` service.
//
// Flow: test -> build (no push) -> scan -> push (only if scan passed) -> update dev overlay
//       -> [manual approval] -> open PR that promotes the SAME tag to the prod overlay.
// Jenkins NEVER talks to Kubernetes. Argo CD pulls the desired state from the GitOps repo.
//
// Anything marked PLACEHOLDER / PSEUDOCODE is environment specific and was not run against real
// infrastructure (no Jenkins, registry or Git server was available for this exercise).

pipeline {

  // Ephemeral, single-use build pod on the CI Kubernetes cluster (Jenkins Kubernetes plugin).
  // Kaniko builds images WITHOUT a Docker daemon and WITHOUT privileged containers.
  agent {
    kubernetes {
      yaml '''
        apiVersion: v1
        kind: Pod
        spec:
          restartPolicy: Never
          containers:
            - name: python
              image: python:3.12-slim
              command: ["sleep"]
              args: ["infinity"]
            - name: kaniko
              image: gcr.io/kaniko-project/executor:debug   # pin by digest in real use
              command: ["sleep"]
              args: ["infinity"]
            - name: tools                                    # trivy, crane, kustomize, git, gh
              image: registry.example.com/aeon/ci-tools:1.0.0  # PLACEHOLDER internal image
              command: ["sleep"]
              args: ["infinity"]
      '''
      defaultContainer 'tools'
    }
  }

  options {
    timeout(time: 30, unit: 'MINUTES')
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timestamps()
    skipDefaultCheckout(true)
  }

  environment {
    REGISTRY   = 'registry.example.com'                         // PLACEHOLDER (e.g. <acct>.dkr.ecr.<region>.amazonaws.com)
    IMAGE_REPO = "${REGISTRY}/aeon/api"
    GITOPS_URL = 'https://git.example.com/aeon/api-gitops.git'  // PLACEHOLDER
  }

  stages {

    stage('Checkout') {
      steps {
        checkout scm
        script {
          // Immutable identifier: the full commit SHA that was tested.
          env.GIT_SHA = sh(script: 'git rev-parse --short=12 HEAD', returnStdout: true).trim()
          env.IMAGE   = "${env.IMAGE_REPO}:${env.GIT_SHA}"
        }
      }
    }

    stage('Unit tests') {
      steps {
        container('python') {
          sh 'cd app && python -I -m unittest -v'
        }
      }
    }

    stage('Secret scan (source)') {
      steps {
        // Fail the build if a credential is committed to the application repo.
        sh 'trivy fs --scanners secret --exit-code 1 --no-progress .'
      }
    }

    stage('Build image (no push)') {
      steps {
        container('kaniko') {
          // --no-push + --tar-path: image stays local until it has been scanned.
          sh '''
            /kaniko/executor \
              --context "$WORKSPACE" \
              --dockerfile "$WORKSPACE/Dockerfile" \
              --build-arg APP_VERSION="$GIT_SHA" \
              --destination "$IMAGE" \
              --no-push --tar-path "$WORKSPACE/image.tar" \
              --reproducible
          '''
        }
      }
    }

    stage('Vulnerability scan') {
      steps {
        // Non-zero exit on HIGH/CRITICAL (with a fix available) stops the pipeline BEFORE the push.
        sh '''
          trivy image --input "$WORKSPACE/image.tar" \
            --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --no-progress
        '''
      }
    }

    // Everything below only runs for the main branch. Feature branches stop after the scan.
    stage('Push image') {
      when { branch 'main' }
      steps {
        // Credentials come from the Jenkins credential store (file credential holding a docker
        // config.json). For ECR prefer an IAM role for the agent (IRSA) + the ECR credential helper,
        // which needs no stored secret at all. Values are masked in logs and never in the repo.
        withCredentials([file(credentialsId: 'registry-docker-config', variable: 'DOCKER_CONFIG_FILE')]) {
          sh '''
            mkdir -p "$WORKSPACE_TMP/dockercfg"
            cp "$DOCKER_CONFIG_FILE" "$WORKSPACE_TMP/dockercfg/config.json"
            export DOCKER_CONFIG="$WORKSPACE_TMP/dockercfg"
            crane push "$WORKSPACE/image.tar" "$IMAGE"
            crane digest "$IMAGE" > "$WORKSPACE/image.digest"
            rm -rf "$WORKSPACE_TMP/dockercfg"
          '''
        }
        // The registry repository must have tag immutability enabled (ECR: imageTagMutability=IMMUTABLE),
        // so a pushed SHA tag can never be overwritten.
      }
    }

    stage('Update dev overlay (GitOps)') {
      when { branch 'main' }
      steps {
        // Controlled commit by a bot account whose write access is limited to this repo.
        withCredentials([usernamePassword(credentialsId: 'gitops-bot',
                                          usernameVariable: 'GIT_USER',
                                          passwordVariable: 'GIT_TOKEN')]) {
          sh '''
            # Token is supplied through GIT_ASKPASS so it never appears in the URL or process list.
            printf '#!/bin/sh\\necho "$GIT_TOKEN"\\n' > "$WORKSPACE_TMP/askpass.sh"
            chmod 700 "$WORKSPACE_TMP/askpass.sh"
            export GIT_ASKPASS="$WORKSPACE_TMP/askpass.sh" GIT_TERMINAL_PROMPT=0

            rm -rf gitops-repo
            git clone "https://${GIT_USER}@${GITOPS_URL#https://}" gitops-repo
            cd gitops-repo
            git config user.name  "jenkins-bot"
            git config user.email "jenkins-bot@example.com"

            cd gitops/overlays/dev
            kustomize edit set image "${IMAGE_REPO}=${IMAGE}"
            cd ../../..

            git add gitops/overlays/dev/kustomization.yaml
            git commit -m "dev: api -> ${GIT_SHA}" \
                       -m "digest: $(cat "$WORKSPACE/image.digest")" \
                       -m "build: ${BUILD_URL}"
            git push origin HEAD:main
          '''
        }
      }
    }

    stage('Promote to prod (pull request)') {
      when { branch 'main' }
      steps {
        // Human gate: someone confirms dev is healthy before a prod PR exists.
        timeout(time: 24, unit: 'HOURS') {
          input message: "Open prod promotion PR for ${env.GIT_SHA}?", ok: 'Open PR',
                submitter: 'release-managers'
        }
        withCredentials([usernamePassword(credentialsId: 'gitops-bot',
                                          usernameVariable: 'GIT_USER',
                                          passwordVariable: 'GIT_TOKEN'),
                         string(credentialsId: 'argocd-readonly-token', variable: 'ARGOCD_AUTH_TOKEN')]) {
          sh '''
            printf '#!/bin/sh\\necho "$GIT_TOKEN"\\n' > "$WORKSPACE_TMP/askpass.sh"
            chmod 700 "$WORKSPACE_TMP/askpass.sh"
            export GIT_ASKPASS="$WORKSPACE_TMP/askpass.sh" GIT_TERMINAL_PROMPT=0
            export GH_TOKEN="$GIT_TOKEN"

            # PSEUDOCODE guard 1: the dev Argo CD app must be Synced + Healthy on THIS tag.
            #   argocd app get api-dev -o json | jq -e '.status.health.status=="Healthy"
            #        and .status.sync.status=="Synced"'
            # PSEUDOCODE guard 2: the tag promoted is read from the dev overlay on main, which only
            #   this pipeline writes after tests + scan passed - never a free-form value.
            rm -rf gitops-repo
            git clone "https://${GIT_USER}@${GITOPS_URL#https://}" gitops-repo
            cd gitops-repo
            git config user.name  "jenkins-bot"
            git config user.email "jenkins-bot@example.com"

            DEV_TAG=$(cd gitops/overlays/dev && kustomize build . | grep -o "${IMAGE_REPO}:[A-Za-z0-9._-]*" | head -1 | cut -d: -f2)
            [ "$DEV_TAG" = "$GIT_SHA" ] || { echo "dev overlay does not carry $GIT_SHA; refusing to promote"; exit 1; }

            BRANCH="promote/api-${GIT_SHA}"
            git checkout -b "$BRANCH"
            (cd gitops/overlays/prod && kustomize edit set image "${IMAGE_REPO}=${IMAGE_REPO}:${DEV_TAG}")
            git add gitops/overlays/prod/kustomization.yaml
            git commit -m "prod: api -> ${DEV_TAG}"
            git push origin "$BRANCH"

            # PSEUDOCODE for GitHub; use the equivalent API for GitLab/Bitbucket.
            gh pr create --base main --head "$BRANCH" \
              --title "Promote api ${DEV_TAG} to prod" \
              --body "Same image already running in dev. Build: ${BUILD_URL}. Requires CODEOWNERS approval."
          '''
        }
      }
    }
  }

  post {
    always {
      // Remove anything that could contain credentials or build artefacts.
      sh 'rm -rf gitops-repo image.tar "$WORKSPACE_TMP" || true'
    }
    failure {
      // PSEUDOCODE: notify the team (Slack/email). A failed scan or test means nothing was pushed.
      echo "Pipeline failed at stage: ${env.STAGE_NAME}. No image was pushed unless the push stage succeeded."
    }
  }
}
