// 이 서비스워커는 두 가지 일을 한다.
//  1) 앱(index.html)이 안 열려있을 때도(백그라운드, 완전히 닫힘 포함) 알림을
//     받는다 — Firebase Cloud Messaging의 표준 방식. "언제 보낼지"는 서버
//     (Cloud Functions) 몫이고, 여기서는 서버가 보낸 알림을 띄우기만 한다.
//  2) 브라우저가 이 사이트를 "설치할 수 있는 앱"으로 인정하게 한다 — 설치하면
//     주소창·탭 없는 별도 창으로 열리고 작업표시줄/바탕화면에 아이콘이 생긴다.
//
// 아래 두 블록의 순서가 중요하다: 설치형 앱에 필요한 처리를 먼저 등록해두고,
// Firebase 라이브러리 불러오기는 try/catch로 감싼다. 예전에는 이 라이브러리를
// 파일 맨 위에서 그냥 불러왔는데, 그 주소(gstatic)를 한 번이라도 못 받아오면
// 서비스워커 전체가 통째로 등록 실패해서 알림도 설치도 다 안 되는 구조였다.

// ===== 설치형 앱(PWA)에 필요한 처리 =====
// 브라우저는 서비스워커에 fetch 처리가 있어야 설치를 허용한다. 다만 이 앱은
// 수시로 업데이트되므로 캐시는 절대 두지 않는다 — 캐시를 두면 고친 내용이
// 반영 안 된 옛 화면이 계속 뜰 수 있다. 그래서 같은 출처의 GET 요청을
// 네트워크에서 그대로 가져오기만 하고, 나머지는 브라우저 기본 동작에 맡긴다.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let sameOrigin = false;
  try { sameOrigin = new URL(req.url).origin === self.location.origin; } catch (e) { return; }
  if (!sameOrigin) return;
  event.respondWith(fetch(req));
});

// 새로 배포된 서비스워커가 곧바로 적용되도록 한다(탭을 다 닫았다 열지 않아도 됨).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// 알림을 눌렀을 때 앱 화면으로 이동(이미 열려있는 탭이 있으면 그걸 포커스).
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow('./index.html');
    })
  );
});

// ===== 알림(Firebase Cloud Messaging) =====
// 라이브러리를 못 받아와도 위의 설치형 앱 기능은 그대로 살아있도록 감싼다.
try {
  importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
  importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

  firebase.initializeApp({
    apiKey: "AIzaSyCRUnr99J5LPYOS-BmeG_peLJ6mLw-w1WM",
    projectId: "chanho-3f3b7",
    messagingSenderId: "304217868567",
    appId: "1:304217868567:web:de51cbc01b517a98a10f52"
  });

  const messaging = firebase.messaging();

  messaging.onBackgroundMessage((payload) => {
    const title = (payload.notification && payload.notification.title) || '찬호의 업무프로그램';
    const options = {
      body: (payload.notification && payload.notification.body) || '',
      icon: (payload.notification && payload.notification.icon) || undefined,
      data: payload.data || {},
    };
    self.registration.showNotification(title, options);
  });
} catch (err) {
  // 알림 기능만 이번 실행에서 빠지고, 앱 설치·화면 표시는 정상 동작한다.
  console.warn('알림 준비 실패(앱 사용에는 지장 없음)', err);
}
