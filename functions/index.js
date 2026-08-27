// 새 가입 신청 / 새 문의 접수를 감지해서 관리자 기기(휴대폰 홈화면 설치 +
// PC 브라우저)로 푸시 알림을 보내는 서버 코드. 클라이언트(index.html)는
// "어느 기기로 보낼지"(FCM 토큰)만 app_data/fcm-admin-tokens에 등록해두고,
// "언제·무엇을 보낼지" 판단과 실제 발송은 여기서 전부 처리한다.
const { onDocumentCreated, onDocumentUpdated, onDocumentWritten } = require("firebase-functions/v2/firestore");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");
const { getMessaging } = require("firebase-admin/messaging");

initializeApp();
const db = getFirestore();

// app_data/{key} 문서 하나에서 값을 읽어온다 — 클라이언트의 saveFileToStorage/
// loadFileFromStorage와 같은 규칙(storedIn: 'firestore' | 'storage')을 그대로
// 따른다. 알림 대상 목록(fcm-admin-tokens)이나 문의 목록(inquiry-list)이
// 나중에 커져서 storage로 넘어가도 안전하게 계속 동작하도록 대비해둔다.
async function readAppData(key) {
  const snap = await db.collection("app_data").doc(key).get();
  if (!snap.exists) return null;
  const data = snap.data();
  if (data.storedIn === "storage") {
    const { getStorage } = require("firebase-admin/storage");
    const [buf] = await getStorage().bucket().file(key).download();
    return buf.toString("utf8");
  }
  return data.value || null;
}

// 등록된 관리자 기기 전부에게 알림을 보내고, 이미 삭제되었거나 만료된
// 토큰(재설치·알림 꺼짐 등)은 목록에서 지워서 다음부터는 헛수고하지 않게 한다.
async function sendToAdminTokens(title, body, data) {
  const text = await readAppData("fcm-admin-tokens");
  const tokens = text ? JSON.parse(text) : [];
  if (!tokens.length) return;

  const res = await getMessaging().sendEachForMulticast({
    tokens,
    notification: { title, body },
    data: data || {},
  });

  const deadTokens = new Set();
  res.responses.forEach((r, i) => {
    if (!r.success && (r.error?.code === "messaging/registration-token-not-registered" ||
                        r.error?.code === "messaging/invalid-registration-token")) {
      deadTokens.add(tokens[i]);
    }
  });
  if (deadTokens.size) {
    const alive = tokens.filter((t) => !deadTokens.has(t));
    await db.collection("app_data").doc("fcm-admin-tokens").set({
      storedIn: "firestore",
      value: JSON.stringify(alive),
      updatedAt: new Date(),
    });
  }
}

// ---------- 새 가입 신청 ----------
// users/{userId} 문서는 앱의 회원가입 화면에서 approved:false로 생성되므로
// (Firestore 보안규칙이 그렇게 강제함), 새 문서가 생기는 것 자체가 곧
// "새 가입 신청 1건"이다.
exports.onNewUserSignup = onDocumentCreated("users/{userId}", async (event) => {
  const data = event.data?.data();
  if (!data) return;
  const email = data.email || "(이메일 없음)";
  await sendToAdminTokens(
    "새 가입 신청",
    `${email}님이 가입을 신청했습니다. 승인관리 탭에서 확인해주세요.`,
    { type: "signup", tab: "adminApproval" }
  );
});

// ---------- 새 문의 접수 ----------
// 문의 목록은 앱 내부에서 "app_data/inquiry-list" 문서 하나의 JSON 배열로
// 통째로 저장/갱신된다(항목마다 별도 문서가 아님) — 그래서 onCreate가 아니라
// onUpdate에서 갱신 전(before)·후(after) 배열을 id 기준으로 비교해서 새로
// 추가된 항목만 골라낸다.
exports.onNewInquiry = onDocumentUpdated("app_data/inquiry-list", async (event) => {
  const beforeRaw = event.data?.before?.data();
  const afterRaw = event.data?.after?.data();
  if (!afterRaw) return;

  const parseList = (raw) => {
    if (!raw || raw.storedIn === "storage" || !raw.value) return [];
    try { return JSON.parse(raw.value); } catch (e) { return []; }
  };
  const before = parseList(beforeRaw);
  const after = parseList(afterRaw);
  if (!after.length) return;

  const beforeIds = new Set(before.map((it) => it.id));
  const added = after.filter((it) => !beforeIds.has(it.id));
  if (!added.length) return;

  if (added.length === 1) {
    const it = added[0];
    await sendToAdminTokens(
      "새 문의 접수",
      `[${it.region || "지역 미상"}] ${it.customer || "고객명 미상"} — ${(it.detail || "").slice(0, 40)}`,
      { type: "inquiry", tab: "inquiry" }
    );
  } else {
    await sendToAdminTokens(
      "새 문의 접수",
      `새 문의 ${added.length}건이 접수되었습니다. 문의 대응 탭에서 확인해주세요.`,
      { type: "inquiry", tab: "inquiry" }
    );
  }
});

// ---------- 특정 사람에게 건별 알림 보내기 ----------
// 승인된 사용자별 기기 토큰은 fcm-admin-tokens(관리자 일괄 알림용)와 별도로
// app_data/fcm-user-tokens에 uid를 키로 저장돼 있다({ [uid]: {email, tokens[]} }).
// 죽은 토큰은 그 uid의 배열에서만 지운다(다른 사람 토큰은 건드리지 않음).
async function sendToUserTokens(uid, title, body, data) {
  if (!uid) return;
  const text = await readAppData("fcm-user-tokens");
  const usersMap = text ? JSON.parse(text) : {};
  const entry = usersMap[uid];
  const tokens = (entry && entry.tokens) || [];
  if (!tokens.length) return;

  const res = await getMessaging().sendEachForMulticast({
    tokens,
    notification: { title, body },
    data: data || {},
  });

  const deadTokens = new Set();
  res.responses.forEach((r, i) => {
    if (!r.success && (r.error?.code === "messaging/registration-token-not-registered" ||
                        r.error?.code === "messaging/invalid-registration-token")) {
      deadTokens.add(tokens[i]);
    }
  });
  if (deadTokens.size) {
    usersMap[uid] = { ...entry, tokens: tokens.filter((t) => !deadTokens.has(t)) };
    await db.collection("app_data").doc("fcm-user-tokens").set({
      storedIn: "firestore",
      value: JSON.stringify(usersMap),
      updatedAt: new Date(),
    });
  }
}

// 알림 큐도 문의 목록과 같은 방식(문서 하나에 JSON 배열 통째로)이라 새로
// 추가된 항목만 골라 발송한다. onDocumentUpdated가 아니라 onDocumentWritten을
// 쓰는 이유: 이 문서는 이번이 처음 만들어지는 경우(맨 첫 알림)에는 "생성"
// 이벤트라서 onUpdate로는 그 첫 건을 놓치기 때문이다.
exports.onNotificationQueued = onDocumentWritten("app_data/notification-queue", async (event) => {
  const beforeRaw = event.data?.before?.exists ? event.data.before.data() : null;
  const afterRaw = event.data?.after?.exists ? event.data.after.data() : null;
  if (!afterRaw) return;

  const parseList = (raw) => {
    if (!raw || raw.storedIn === "storage" || !raw.value) return [];
    try { return JSON.parse(raw.value); } catch (e) { return []; }
  };
  const before = parseList(beforeRaw);
  const after = parseList(afterRaw);
  if (!after.length) return;

  const beforeIds = new Set(before.map((it) => it.id));
  const added = after.filter((it) => !beforeIds.has(it.id));
  if (!added.length) return;

  for (const item of added) {
    await sendToUserTokens(
      item.toUid,
      item.title || "알림",
      item.body || "",
      { type: "case-notify", caseId: item.caseId || "" }
    );
  }
});
