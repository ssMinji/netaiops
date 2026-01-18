#!/bin/bash
#
# NetAIOps CloudFormation 스택 배포 스크립트
# 사용법: ./deploy.sh [command] [options]
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 기본 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS_REGION="${AWS_REGION:-us-east-1}"

# 스택 이름 설정
STACK_SAMPLE_APP="netaiops-sample-app"
STACK_NFM_ENABLE="netaiops-nfm-enable"
STACK_NFM_SETUP="netaiops-nfm-setup"
STACK_COGNITO="netaiops-cognito"
STACK_MODULES="netaiops-modules"
STACK_TRAFFIC_MIRROR="netaiops-traffic-mirror"

# 함수: 로그 출력
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 함수: 스택 배포
deploy_stack() {
    local stack_name=$1
    local template_file=$2
    shift 2
    local params=("$@")

    log_info "배포 중: $stack_name"

    local cmd="aws cloudformation deploy \
        --template-file ${SCRIPT_DIR}/${template_file} \
        --stack-name ${stack_name} \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region ${AWS_REGION}"

    if [ ${#params[@]} -gt 0 ]; then
        cmd+=" --parameter-overrides ${params[*]}"
    fi

    if eval $cmd; then
        log_success "$stack_name 배포 완료"
    else
        log_error "$stack_name 배포 실패"
        return 1
    fi
}

# 함수: 스택 상태 확인
check_stack_status() {
    local stack_name=$1
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND"
}

# 함수: 스택 삭제
delete_stack() {
    local stack_name=$1
    log_info "삭제 중: $stack_name"

    if aws cloudformation delete-stack --stack-name "$stack_name" --region "$AWS_REGION" 2>/dev/null; then
        log_info "삭제 대기 중: $stack_name"
        aws cloudformation wait stack-delete-complete --stack-name "$stack_name" --region "$AWS_REGION" 2>/dev/null || true
        log_success "$stack_name 삭제 완료"
    else
        log_warn "$stack_name 스택이 존재하지 않거나 이미 삭제됨"
    fi
}

# 함수: 사용법 출력
show_usage() {
    cat << EOF
NetAIOps CloudFormation 배포 스크립트

사용법: $0 [command] [options]

Commands:
  deploy-all          모든 스택 순차 배포
  deploy-base         기본 인프라만 배포 (sample-app)
  deploy-nfm          Network Flow Monitor 배포 (enable + setup)
  deploy-cognito      Cognito 인증 스택 배포
  deploy-modules      모듈 설치 스택 배포
  deploy-traffic      Traffic Mirroring 스택 배포

  delete-all          모든 스택 삭제 (역순)
  delete [stack]      특정 스택 삭제

  status              모든 스택 상태 확인
  list                배포된 스택 목록

Options:
  --region REGION     AWS 리전 (기본: us-east-1)
  --db-password PWD   DB 비밀번호 (기본: ReInvent2025!)
  -h, --help          도움말

Examples:
  $0 deploy-all
  $0 deploy-base --db-password MySecurePass123!
  $0 status
  $0 delete-all

EOF
}

# 함수: 모든 스택 상태 확인
show_status() {
    log_info "스택 상태 확인 중..."
    echo ""
    printf "%-30s %-20s\n" "스택 이름" "상태"
    echo "------------------------------------------------"

    for stack in "$STACK_SAMPLE_APP" "$STACK_NFM_ENABLE" "$STACK_NFM_SETUP" \
                 "$STACK_COGNITO" "$STACK_MODULES" "$STACK_TRAFFIC_MIRROR"; do
        status=$(check_stack_status "$stack")
        printf "%-30s %-20s\n" "$stack" "$status"
    done
}

# 함수: 기본 인프라 배포
deploy_base() {
    local db_password="${1:-ReInvent2025!}"
    deploy_stack "$STACK_SAMPLE_APP" "sample-appication.yaml" \
        "DBPassword=$db_password"
}

# 함수: NFM 배포
deploy_nfm() {
    # 1. NFM Enable
    deploy_stack "$STACK_NFM_ENABLE" "network-flow-monitor-enable.yaml"

    # 2. NFM Setup
    deploy_stack "$STACK_NFM_SETUP" "network-flow-monitor-setup.yaml" \
        "SampleApplicationStackName=$STACK_SAMPLE_APP" \
        "NetworkFlowMonitorEnableStackName=$STACK_NFM_ENABLE"
}

# 함수: Cognito 배포
deploy_cognito() {
    deploy_stack "$STACK_COGNITO" "a2a-performance-agentcore-cognito.yaml"
}

# 함수: 모듈 배포
deploy_modules() {
    deploy_stack "$STACK_MODULES" "module3-combined-setup.yaml" \
        "SampleApplicationStackName=$STACK_SAMPLE_APP"
}

# 함수: Traffic Mirroring 배포
deploy_traffic() {
    deploy_stack "$STACK_TRAFFIC_MIRROR" "trffice-mirroring-setup.yaml" \
        "SampleApplicationStackName=$STACK_SAMPLE_APP" \
        "NetworkFlowMonitorStackName=$STACK_NFM_SETUP"
}

# 함수: 전체 배포
deploy_all() {
    local db_password="${1:-ReInvent2025!}"

    log_info "=== NetAIOps 전체 스택 배포 시작 ==="
    echo ""

    # 1단계: 기본 인프라
    log_info "[1/5] 기본 애플리케이션 인프라 배포"
    deploy_base "$db_password"

    # 2단계: 병렬 배포 가능 스택들
    log_info "[2/5] NFM Enable 배포"
    deploy_stack "$STACK_NFM_ENABLE" "network-flow-monitor-enable.yaml"

    log_info "[3/5] Cognito 및 모듈 배포"
    deploy_cognito
    deploy_modules

    # 3단계: NFM Setup
    log_info "[4/5] NFM Setup 배포"
    deploy_stack "$STACK_NFM_SETUP" "network-flow-monitor-setup.yaml" \
        "SampleApplicationStackName=$STACK_SAMPLE_APP" \
        "NetworkFlowMonitorEnableStackName=$STACK_NFM_ENABLE"

    # 4단계: Traffic Mirroring
    log_info "[5/5] Traffic Mirroring 배포"
    deploy_traffic

    echo ""
    log_success "=== 전체 배포 완료 ==="
    show_status
}

# 함수: 전체 삭제 (역순)
delete_all() {
    log_info "=== NetAIOps 전체 스택 삭제 시작 ==="
    log_warn "모든 리소스가 삭제됩니다. 계속하시겠습니까? (y/N)"
    read -r confirm

    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        log_info "삭제 취소됨"
        return 0
    fi

    # 역순 삭제
    delete_stack "$STACK_TRAFFIC_MIRROR"
    delete_stack "$STACK_NFM_SETUP"
    delete_stack "$STACK_MODULES"
    delete_stack "$STACK_COGNITO"
    delete_stack "$STACK_NFM_ENABLE"
    delete_stack "$STACK_SAMPLE_APP"

    log_success "=== 전체 삭제 완료 ==="
}

# 메인 로직
main() {
    local command="${1:-}"
    local db_password="ReInvent2025!"

    # 옵션 파싱
    shift || true
    while [[ $# -gt 0 ]]; do
        case $1 in
            --region) AWS_REGION="$2"; shift 2 ;;
            --db-password) db_password="$2"; shift 2 ;;
            -h|--help) show_usage; exit 0 ;;
            *) shift ;;
        esac
    done

    case "$command" in
        deploy-all)     deploy_all "$db_password" ;;
        deploy-base)    deploy_base "$db_password" ;;
        deploy-nfm)     deploy_nfm ;;
        deploy-cognito) deploy_cognito ;;
        deploy-modules) deploy_modules ;;
        deploy-traffic) deploy_traffic ;;
        delete-all)     delete_all ;;
        delete)         delete_stack "$2" ;;
        status)         show_status ;;
        list)           show_status ;;
        -h|--help|"")   show_usage ;;
        *)              log_error "알 수 없는 명령: $command"; show_usage; exit 1 ;;
    esac
}

main "$@"
