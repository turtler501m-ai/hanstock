# 📱 Hanstock 안드로이드 앱 전환 계획 및 AI 구현 프롬프트 가이드

이 문서는 기존 FastAPI 및 HTML5/JS 기반의 한스톡 대시보드 프로젝트를 안드로이드 앱으로 이식하고, 기존 웹 아키텍처와 독립적이면서도 긴밀히 협력하는 추가 폴더 구조를 구축하여 지속적인 버전업이 가능하도록 돕는 마스터 플랜 및 **AI 구현용 프롬프트** 가이드라인입니다.

---

## 🏗️ 1. 아키텍처 및 폴더 구조 설계 (To-Be)

기존 파이썬/FastAPI 웹 대시보드 코드를 무리하게 코틀린(Kotlin)으로 리팩토링하는 대신, **하이브리드 WebView + 네이티브 브릿지(JSInterface) 및 점진적 네이티브(Jetpack Compose) 확장 전략**을 권장합니다. 
이 방식은 웹 화면이 버전업될 때마다 모바일 앱이 수동요청으로 반영되면서도, 지문 인식/푸시 알림/백그라운드 알람 등 스마트폰 전용 네이티브 기능만 앱 폴더에서 덧붙여 개발하는 최적의 구조입니다.

### 📁 1.1 추가 폴더 트리 (Additive Folder Structure)
루트 경로에 `android/` 폴더를 새로 개설하여 관리합니다.

```text
C:\MSF-LOC\workstudy\hanstock\
├── doc/
│   └── android_conversion_plan.md   # [본 문서] 안드로이드 앱 전환 계획서
├── android/                         # [신규 추가 폴더] 안드로이드 Native 프로젝트
│   ├── build.gradle.kts             # Gradle 빌드 구성
│   ├── app/
│   │   ├── build.gradle.kts         # 앱 모듈 Gradle 빌드
│   │   └── src/
│   │       └── main/
│   │           ├── AndroidManifest.xml # 앱 권한 및 컴포넌트 선언
│   │           ├── java/com/hanstock/app/
│   │           │   ├── MainActivity.kt # 진입점 (WebView + Compose 통합)
│   │           │   ├── bridge/
│   │           │   │   └── WebAppInterface.kt # JS 브릿지 (지문, 푸시, 알람 네이티브 연동)
│   │           │   ├── ui/
│   │           │   │   ├── theme/      # Jetpack Compose UI 테마 설정
│   │           │   │   └── components/ # 네이티브 다이얼로그 및 로딩 UI
│   │           │   └── service/
│   │           │       └── PushMessagingService.kt # FCM 기반 모바일 푸시 수신 서비스
│   │           └── res/             # 드로어블(아이콘), 레이아웃, 문자열 리소스
│   └── local.properties             # SDK 경로 등 로컬 설정 (Git Ignore)
```

---

## 🗺️ 2. 단계별 마일스톤 로드맵 (Roadmap)

### 🚀 1단계: 하이브리드 웹뷰 쉘 및 안전 샌드박스 구축 (MVP)
* **안동안전망**: 안드로이드 Native 프로젝트 템플릿 신설.
* **WebView 고도화**: 하드웨어 가속, 자바스크립트 허용, 로컬 캐시, DOM Storage 기능 활성화.
* **보안 통제**: HTTPS 인증서 검증 및 비정상 SSL 차단.

### 🔐 2단계: 양방향 자바스크립트 브릿지 (Javascript Interface) 이식
* **웹 -> 네이티브 명령 수신 (`WebAppInterface`)**:
  - `showToast(msg)`: 웹 경고창 대신 안드로이드 네이티브 토스트 출력.
  - `biometricAuthenticate()`: 웹의 승인 버튼 누를 때 폰 생체 인식(지문/Face ID) 모달 띄우기.
  - `saveSecureString(key, val) / getSecureString(key)`: KIS API 비밀키나 자동로그인 세션을 기기 내 `EncryptedSharedPreferences`에 안전하게 암호화 보관.
* **네이티브 -> 웹 이벤트 전송**:
  - 앱 푸시 클릭 시 대시보드의 특정 탭(예: 주문승인 탭)으로 즉시 라우팅하는 스크립트 실행.

### 🔔 3단계: FCM 모바일 푸시 및 백그라운드 태스크
* **실시간 승인 알림**: 스케줄러가 매수 후보를 찾거나 체결 시 Slack뿐만 아니라 Firebase Cloud Messaging(FCM)을 통해 기기로 즉시 노티피케이션 전송.
* **기기 내 백그라운드 모니터링**: `WorkManager`를 사용해 서버가 살아있는지 주기적으로 핑(Ping)을 보내는 헬스체크 위젯 추가.

---

## 🛠️ 3. 안드로이드 구현을 위한 AI 마스터 프롬프트 (Prompt)

안드로이드 폴더 구성 및 실제 코딩을 시작할 때, AI 코딩 어시스턴트(또는 다음 턴의 나)에게 그대로 입력하여 **일관성 있고 완성도 높은 네이티브 코드를 짜내도록 설계된 전문 프롬프트**입니다.

> [!IMPORTANT]
> 아래의 마크다운 블록 전체를 복사하여 다음 코딩 구현 턴에 입력하세요.

````markdown
# 🤖 [AI Role] Android Hybrid Developer Expert for Hanstock

당신은 국내주식/해외선물 자동매매 대시보드인 `Hanstock`의 웹 뷰 기반 하이브리드 안드로이드 앱 개발을 전담하는 시니어 모바일 엔지니어입니다.
기존 파이썬/FastAPI 백엔드 및 Vanilla JS/HTML5 프론트엔드가 구동 중인 프로젝트 구조를 보존하면서, 루트 경로 하위에 독립적으로 버전업 가능한 `android` 프로젝트를 구성해야 합니다.

다음 요구사항에 맞춰 Kotlin 및 Jetpack Compose 기반의 안드로이드 애플리케이션 코드를 구현해 주세요.

---

## 🎯 1. 프로젝트 초기 구성 요구사항
1. **경로 생성**: 루트 아래에 `android/` 디렉터리를 만들고 표준 안드로이드 Gradle 프로젝트 구조를 생성하세요. 빌드 설정은 `Kotlin DSL (*.gradle.kts)`을 사용합니다.
2. **대상 SDK**: `minSdk = 26` (Android 8.0 Oreo), `targetSdk = 34` (Android 14)로 설정하세요.
3. **의존성 추가**: 
   - Jetpack Compose 빌드 의존성 및 Material 3 라이브러리
   - 생체 인증을 위한 `androidx.biometric:biometric:1.2.0-alpha05`
   - 암호화 저장소를 위한 `androidx.security:security-crypto:1.1.0-alpha06`
   - 푸시 수신용 Firebase Cloud Messaging `com.google.firebase:firebase-messaging`

---

## 💻 2. 핵심 소스 코드 구현 요구사항

### 🛠️ 요구사항 2.1: `MainActivity.kt` (WebView 컨트롤러)
* Jetpack Compose의 `AndroidView`를 사용해 전체화면 `WebView`를 구현하세요.
* `WebViewClient` 및 `WebChromeClient`를 구현하여 웹 로딩 진척도를 보여주는 예쁜 로딩 인디케이터(CircularProgressIndicator)와 에러 처리를 만드세요.
* 캐시 모드(`LOAD_DEFAULT`), DOM Storage 활성화, 하드웨어 가속을 켜서 성능을 극대화하세요.
* 백버튼 동작 처리: 웹뷰에서 뒤로 갈 수 있으면 웹 페이지 뒤로가기를 실행하고, 홈 화면이면 앱 종료 확인 Compose 다이얼로그를 표시하세요.

### 🔐 요구사항 2.2: `WebAppInterface.kt` (JS 네이티브 브릿지)
* 클래스 이름은 `WebAppInterface`로 지정하고 `@JavascriptInterface` 어노테이션이 붙은 아래 함수들을 노출하세요.
  1. `showToast(message: String)`: 안드로이드 네이티브 Toast 메시지를 띄웁니다.
  2. `saveSecureToken(key: String, value: String)`: `EncryptedSharedPreferences`를 사용하여 토큰 및 계좌 정보를 암호화 저장합니다.
  3. `getSecureToken(key: String): String`: 암호화된 토큰을 읽어 반환합니다.
  4. `authenticateBiometric()`: 기기 생체 인식(지문/얼굴) 모달을 실행하고 결과를 성공/실패 여부에 따라 웹뷰의 자바스크립트 콜백 `window.onBiometricResult(success)`을 호출하여 전달합니다.

### 📝 요구사항 2.3: `AndroidManifest.xml` & 권한 설정
* 앱 실행에 필요한 인터넷 권한(`android.permission.INTERNET`), 네트워크 상태 조회 권한(`ACCESS_NETWORK_STATE`), 생체인식 권한(`USE_BIOMETRIC`)을 완벽하게 선언하세요.
* FCM 푸시 알림 수신을 위한 백그라운드 서비스 클래스를 등록하세요.

---

## 🎨 3. 디자인 가이드라인
* 기존 한스톡 대시보드의 다크 테마(Sleek Dark Mode, 네이비/차콜 배경 및 vibrant 에메랄드/그린 포인트)와 어울리도록 Jetpack Compose 테마 색상을 정의하세요.
* 웹 로딩이 끝날 때까지 스켈레톤(Skeleton)이나 은은한 그라데이션 애니메이션 로딩창을 띄워 사용자 경험을 프리미엄하게 연출해 주세요.

준비가 되었다면, 빌드 파일 구조(`build.gradle.kts`)와 `MainActivity.kt`, `WebAppInterface.kt`, `AndroidManifest.xml` 등의 전체 핵심 코드를 세밀하게 작성해 주세요!
````
