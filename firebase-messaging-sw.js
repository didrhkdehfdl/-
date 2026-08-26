// 앱(index.html)이 안 열려있을 때도(백그라운드, 완전히 닫힘 포함) 알림을
// 받으려면 이 서비스워커가 필요하다 — Firebase Cloud Messaging의 표준 방식.
// 여기서 실제로 "언제 보낼지"를 정하지는 않는다(그건 서버(Cloud Functions)
// 쪽 몫), 이 파일은 서버가 보낸 알림을 받아서 화면에 띄워주는 역할만 한다.
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
