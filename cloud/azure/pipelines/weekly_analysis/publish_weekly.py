"""파이프라인 완료 후 앱 조회용 결과의 Cosmos 반영.

단계별 Gold 출력과 Cosmos container/partition/id 계약 연결 필요
이 파일에만 외부 저장 호출 배치. 주간 계산 입력으로 Cosmos 사용 제외
"""


def main():
    raise NotImplementedError(
        "Cosmos 반영 코드 및 저장 계약 연결 필요. "
        "파이프라인 일부 실행 성공은 전체 주간 Job 완료와 별개. 현재 저장 수행 없음."
    )


if __name__ == "__main__":
    main()
