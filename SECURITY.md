# Reporting a security problem

*[한국어는 아래에 있습니다.](#보안-문제-신고)*

**Report it privately first.** Not as a public issue, and not on social media.

Use **Report a vulnerability** on this repository's [Security tab](https://github.com/needmoretruth/NeedMoreBench/security/advisories/new). Only you and the maintainer can read the report.

**Write in English or in Korean.** Both are read.

## What to put in it

What you did, what happened, and how it can be seen again. Say which download or version you used and on which system (Windows, macOS or Linux). Screenshots and files can be attached to the report.

## What NeedMoreBench holds, and what it cannot

NeedMoreBench is a desktop app. There is no NeedMoreBench server, and no account.

- **Keys** stay on your computer, in the system password store: Windows Credential Manager, the macOS Keychain, or the keyring on Linux. On a Linux computer without a keyring, a pasted key is kept only until the app closes.
- **Games and records** stay in the app's folder on your computer. A game file leaves only when you export it.
- **Prompts** go only to the services you connect (OpenCode, OpenRouter, Anthropic, Venice) or to LM Studio on your own computer.

That is worth knowing before you write, because it changes what a finding means.

## Scope

This repository: the app, its downloads and the way they are built. A fault in a connected service (its website, its servers, its keys) belongs to that service. Report it to them.

## What is not promised

No bounty, no payment, and no fixed reply time. Reports are read.

---

# 보안 문제 신고

**먼저 비공개로 알려 주십시오.** 공개 이슈나 소셜 미디어에 올리지 말아 주십시오.

이 저장소의 [Security 탭](https://github.com/needmoretruth/NeedMoreBench/security/advisories/new)에서 **Report a vulnerability**를 누릅니다. 신고는 보내신 분과 관리자만 읽을 수 있습니다.

**영어 또는 한국어로 써 주십시오.** 둘 다 읽습니다.

## 무엇을 적어 주시면 되는가

무엇을 하셨고, 무엇이 일어났고, 그것을 다시 볼 수 있는 방법을 적어 주십시오. 어떤 다운로드나 버전을 어느 운영체제(윈도우, macOS, 리눅스)에서 쓰셨는지도 적어 주십시오. 화면 사진과 파일은 신고에 붙일 수 있습니다.

## NeedMoreBench가 무엇을 갖고 있고, 무엇을 못 하는가

NeedMoreBench는 데스크톱 앱입니다. NeedMoreBench 서버도 계정도 없습니다.

- **키**는 내 컴퓨터의 비밀번호 보관함(윈도우 자격 증명 관리자, macOS 키체인, 리눅스 키링)에만 있습니다. 키링이 없는 리눅스 컴퓨터에서는 붙여 넣은 키를 앱을 닫을 때까지만 기억합니다.
- **게임과 기록**은 내 컴퓨터의 앱 폴더에 있습니다. 게임 파일은 내가 내보낼 때만 밖으로 나갑니다.
- **프롬프트**는 내가 연결한 서비스(OpenCode, OpenRouter, Anthropic, Venice)나 내 컴퓨터의 LM Studio로만 갑니다.

그 사실이 어떤 발견이 무엇을 뜻하는지를 바꾸므로, 쓰시기 전에 알아 두실 만합니다.

## 범위

이 저장소의 앱, 다운로드 파일, 그것을 만드는 과정입니다. 연결한 서비스(그 웹사이트, 서버, 키)의 결함은 그 서비스의 것이니 그쪽에 알려 주십시오.

## 약속하지 않는 것

포상금도, 대가 지급도, 정해진 답장 기한도 없습니다. 신고는 읽습니다.
