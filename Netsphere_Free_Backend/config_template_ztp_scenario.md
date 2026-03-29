# Config Template & ZTP 통합 테스트 시나리오

## 1. 시나리오 개요
이 문서는 사용자가 정의한 "표준 관리 설정(Logging & SNMP)"을 템플릿화하고, 이를 **기존 장비에 배포(Day 2)**하거나 **신규 장비 ZTP(Day 0)**를 통해 자동으로 적용하는 전체 프로세스를 검증합니다.

### 🎯 목표 설정값
```cisco
service timestamps log datetime msec
logging host 10.1.3.151
logging trap informational

snmp-server community jjckkjl RO
snmp-server host 10.1.3.151 version 2c jjckkjl
```

---

## 2. [Step 1] Config Template 생성
먼저, 시스템에 위 설정을 표준 템플릿으로 등록합니다.

1. **메뉴 이동**: `Smart Configuration` > `Templates` 탭 클릭.
2. **템플릿 생성**: `+ Create Template` 버튼 클릭.
3. **입력 정보**:
   - **Name**: `Standard_Syslog_SNMP_Profile`
   - **Device Type**: `Cisco IOS` (또는 해당하는 타입)
   - **Content (Jinja2)**: 
     *(변수를 사용하여 재사용성을 높일 수도 있지만, 이번 테스트에서는 고정값을 사용합니다)*
     ```jinja2
     service timestamps log datetime msec
     logging host 10.1.3.151
     logging trap informational
     !
     snmp-server community jjckkjl RO
     snmp-server host 10.1.3.151 version 2c jjckkjl
     ```
4. **저장**: `Create` 버튼을 눌러 저장합니다.

---

## 3. [Step 2] Compliance Check (설정 검증)
기존 장비들이 이 표준 설정을 잘 따르고 있는지 검사합니다.

1. **메뉴 이동**: `Smart Configuration` > `Compliance` (또는 장비 상세 페이지의 Compliance 탭).
2. **검사 실행**:
   - 대상 장비 선택 (예: `10.250.4.2`).
   - 비교할 템플릿으로 방금 만든 `Standard_Syslog_SNMP_Profile` 선택.
   - `Run Check` 클릭.
3. **결과 확인**:
   - **Compliant (녹색)**: 이미 설정이 완벽하게 들어있는 경우.
   - **Non-Compliant (적색)**: 설정이 누락되거나 다른 경우.
   - **Diff View**: 누락된 설정(`+ logging host...`)이 붉은색/초록색으로 표시되는지 확인합니다.

---

## 4. [Step 3] Template Deploy (설정 배포)
설정이 누락된 장비에 템플릿을 배포하여 설정을 맞춥니다.

1. **배포 실행**: 
   - 템플릿 목록에서 `Standard_Syslog_SNMP_Profile`의 `Deploy` 아이콘(비행기 모양) 클릭.
   - 대상 장비 선택 후 `Deploy Config` 클릭.
2. **진행 상태**: 
   - "Deploying..." 상태 표시 및 성공 메시지 확인.
   - (백엔드 로그에서 SSH 접속 및 명령어 전송 로그 확인 가능)
3. **재검증 (Re-Check)**:
   - 다시 Compliance Check를 수행했을 때 상태가 **Compliant**로 바뀌는지 확인합니다.
   
---

## 5. [Step 4] ZTP (Zero Touch Provisioning) 테스트
신규 장비가 네트워크에 연결되었을 때, 이 템플릿이 자동으로 적용되는지 확인합니다.

1. **ZTP 대기열 확인**:
   - 신규 장비(또는 초기화된 장비)를 네트워크에 연결하고 부팅.
   - 대시보드의 `ZTP Queue` 메뉴에 장비가 `Pending` 상태로 나타나는지 확인.
2. **장비 승인 및 템플릿 할당**:
   - 해당 장비의 `Approve` 버튼 클릭.
   - **Config Template** 옵션에서 `Standard_Syslog_SNMP_Profile` 선택.
   - (선택 사항) Site 할당, Hostname 설정 등 추가 입력.
3. **프로비저닝 시작**:
   - 승인 완료 시, 시스템이 자동으로 장비에 접속하여 템플릿 내용을 밀어넣습니다.
4. **결과 확인**:
   - `ZTP Logs`에서 "Configuration applied successfully" 메시지 확인.
   - 장비가 `Online` 상태로 전환됨.
   - 실제 장비에서 `show run`을 했을 때 `logging host 10.1.3.151` 등이 들어가 있어야 함.

---

## 💡 참고: 변수(Variable) 활용법 (심화)
만약 여러 사이트에서 서버 IP만 다르게 쓰고 싶다면, 템플릿을 다음과 같이 수정하고 **Variables** 기능을 사용하세요.

**Template Content:**
```jinja2
logging host {{ syslog_ip }}
snmp-server community {{ snmp_comm }} RO
```

**Variable Set (예: HQ_Vars):**
```json
{
  "syslog_ip": "10.1.3.151",
  "snmp_comm": "jjckkjl"
}
```
배포 시 템플릿과 변수 세트를 함께 선택하면 됩니다.
