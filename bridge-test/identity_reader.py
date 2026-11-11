"""Read the current Moodle user's identity; never trust a typed email as a cache key."""
from urllib.parse import urlsplit, parse_qs
from playwright.async_api import Error as BrowserError
from moodle_reader import is_authenticated
from student_cache import normalize_email


async def read_identity(page, moodle):
    if not await is_authenticated(page, moodle):
        return None
    owner = await page.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
    profile_page = await page.context.new_page()
    try:
        # Read-only form access gives exact first/last names without guessing word order.
        for path in (f"/user/edit.php?id={owner}", "/user/profile.php"):
            try:
                await profile_page.goto(moodle + path, wait_until="domcontentloaded", timeout=12000)
                location = urlsplit(profile_page.url)
                if location.path not in {"/user/edit.php", "/user/profile.php"}:
                    continue
                if parse_qs(location.query).get("id", [str(owner)]) != [str(owner)]:
                    continue
                if not await is_authenticated(profile_page, moodle):
                    continue
                current = await profile_page.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
                if current != owner:
                    continue
                fields = await profile_page.evaluate("""() => {
                    const value = name => document.querySelector('input[name="'+name+'"]')?.value?.trim() || '';
                    const profile = document.querySelector('.userprofile');
                    const emails = [...(profile?.querySelectorAll('a[href^="mailto:"]') || [])]
                        .map(a=>a.getAttribute('href').slice(7).split('?')[0]);
                    return {
                        email: value('email') || (emails.length===1 ? emails[0] : ''),
                        first_name: value('firstname'), last_name: value('lastname'),
                        display_name: document.querySelector('.usermenu .usertext')?.textContent?.trim() || ''
                    };
                }""")
                fields["email"] = normalize_email(fields["email"])
                fields["moodle_user_id"] = int(owner)
                if not fields["display_name"]:
                    fields["display_name"] = " ".join(filter(None, (fields["first_name"], fields["last_name"])))
                return fields
            except (BrowserError, ValueError):
                continue
        return None
    finally:
        await profile_page.close()
