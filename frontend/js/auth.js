const API_URL = '/api';

// getCookie 함수는 더 이상 필요 없으므로 삭제합니다.

/**
 * 현재 로그인된 사용자 정보를 서버에 요청하는 함수
 */
async function getCurrentUser() {
    // HttpOnly 쿠키는 JS로 읽을 수 없으므로, 쿠키 존재 여부를 미리 확인하지 않습니다.
    // 대신, 브라우저가 자동으로 쿠키를 담아 보내줄 것을 믿고 바로 API를 호출합니다.
    try {
        const response = await fetch(`${API_URL}/auth/me`, {
            method: 'GET',
            credentials: 'include' // 이 옵션 덕분에 브라우저는 HttpOnly 쿠키를 서버로 보냅니다.
        });

        // 서버가 200 OK 응답을 주면, 유효한 세션이 있다는 의미입니다.
        if (response.ok) {
            return await response.json(); // 사용자 정보를 반환합니다.
        }
        // 401 등 다른 응답이 오면, 로그인되지 않은 것으로 간주합니다.
        return null;
    } catch (error) {
        console.error("Failed to fetch current user:", error);
        return null;
    }
}

/**
 * 로그인 상태에 따라 네비게이션 바의 UI를 변경하는 함수
 */
async function renderNavbar() {
    const authLinks = document.getElementById('auth-links');
    if (!authLinks) return;

    const user = await getCurrentUser();
    
    if (user) { // 로그인된 경우
        authLinks.innerHTML = `
            <span class="navbar-text">Welcome, <a href="profile.html" style="cursor: pointer;">${user.username}</a> !</span>
            <span><a href="blog.html" class=>Blog</a></span>
            <a href="#" id="logout-link" class="logout-button-link">Log Out</a>`;
        
        const logoutLink = document.getElementById('logout-link');
        if (logoutLink) {
            // 이 부분을 수정해주세요!
            logoutLink.addEventListener('click', async (event) => {
                event.preventDefault(); // <-- 여기를 추가하여 링크의 기본 동작을 막습니다.

                const logoutResponse = await fetch(`${API_URL}/auth/logout`, {
                    method: 'POST',
                    credentials: 'include'
                });

                if (logoutResponse.ok) {
                    console.log("서버에서 로그아웃 성공.");
                    window.location.href = '/index.html';
                } else {
                    console.error("서버에서 로그아웃 실패.");
                    alert('로그아웃에 실패했습니다.');
                }
            });
        }
    } else {
        authLinksContainer.innerHTML = `
            <a href="/login.html">Log In</a>
            <a href="/signup.html">Sign Up</a>`;
    }
}