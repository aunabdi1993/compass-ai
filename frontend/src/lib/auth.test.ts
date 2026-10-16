import { friendlyAuthError, linkErrorFromUrl } from "./auth";

describe("linkErrorFromUrl", () => {
  it("recognises an expired or used link", () => {
    expect(linkErrorFromUrl("#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired"))
      .toMatch(/expired or was already used/);
  });
  it("gives a generic message for other link errors", () => {
    expect(linkErrorFromUrl("#error=server_error&error_description=Something+broke")).toMatch(/didn't work/);
  });
  it("ignores normal URLs and successful sign-in hashes", () => {
    expect(linkErrorFromUrl("")).toBeNull();
    expect(linkErrorFromUrl("#access_token=abc&refresh_token=def&type=magiclink")).toBeNull();
  });
});

describe("friendlyAuthError", () => {
  it("maps Supabase messages to plain English", () => {
    expect(friendlyAuthError("Token has expired or is invalid")).toMatch(/code didn't work/);
    expect(friendlyAuthError("For security purposes, you can only request this after 52 seconds.")).toMatch(/wait a minute/);
    expect(friendlyAuthError("boom")).toMatch(/Something went wrong/);
  });
});
