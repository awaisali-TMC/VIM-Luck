import Card from "../components/common/Card";

/* Read-only profile. Account data is maintained by the buying organisation —
   suppliers request changes through their AP contact, so there is no client-
   side editing here (a fake edit form is worse than none). */
export default function SupplierProfilePage({ user }) {
  const profile = {
    companyName: user?.company_name || user?.name || "Supplier Company",
    contactPerson: user?.contact_person || user?.name || "—",
    mobile: user?.mobile || "—",
    email: user?.email || "—",
    status: user?.status || "pending",
    registeredSince: user?.created_at || null,
  };

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      {/* Company Header */}
      <Card>
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 rounded-xl flex items-center justify-center text-white text-lg font-bold flex-shrink-0"
            style={{ backgroundColor: "#10B981" }}
          >
            {profile.companyName.slice(0, 2).toUpperCase()}
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-neutral-900 m-0">{profile.companyName}</h2>
            <div className="text-xs text-neutral-500 mt-0.5">
              Supplier Account &middot; {profile.status === "verified" ? (
                <span className="text-success-dark font-semibold">Verified</span>
              ) : (
                <span className="text-warning-dark font-semibold">Pending Verification</span>
              )}
            </div>
            {profile.registeredSince && (
              <div className="text-2xs text-neutral-400 mt-0.5">
                Member since {new Date(profile.registeredSince).toLocaleDateString("en-PK", {
                  month: "long", year: "numeric",
                })}
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Account details */}
      <Card>
        <h3 className="text-xs font-bold text-neutral-800 mb-3 flex items-center gap-2">
          <span>&#127970;</span> Account Details
        </h3>
        <div className="grid grid-cols-2 gap-x-8 gap-y-3">
          <ProfileField label="Company Name" value={profile.companyName} />
          <ProfileField label="Contact Person" value={profile.contactPerson} />
          <ProfileField label="Mobile" value={profile.mobile} />
          <ProfileField label="Email" value={profile.email} />
        </div>
        <div className="mt-4 pt-3 border-t border-neutral-100 text-2xs text-neutral-500">
          Need to update these details? Contact your AP representative — account
          changes are verified and applied by the buying organisation.
        </div>
      </Card>
    </div>
  );
}

function ProfileField({ label, value }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-2xs font-semibold text-neutral-500 w-28 flex-shrink-0">{label}</span>
      <span className="text-xs text-neutral-800">{value}</span>
    </div>
  );
}
