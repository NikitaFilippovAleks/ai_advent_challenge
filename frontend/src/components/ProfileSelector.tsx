import { useState, useEffect } from "react";
import { UserProfile } from "../types";
import { getProfiles, getConversationProfile, setConversationProfile } from "../api/profiles";

interface Props {
  conversationId: string;
  onProfileChange?: () => void;
}

function ProfileSelector({ conversationId, onProfileChange }: Props) {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [source, setSource] = useState<string>("none");

  useEffect(() => {
    loadData();
  }, [conversationId]);

  const loadData = async () => {
    try {
      const [allProfiles, convProfile] = await Promise.all([
        getProfiles(),
        getConversationProfile(conversationId),
      ]);
      setProfiles(allProfiles);
      setSelectedProfileId(convProfile.profile?.id || "");
      setSource(convProfile.source);
    } catch {
      // Ошибка загрузки
    }
  };

  const handleChange = async (value: string) => {
    const profileId = value || null;
    setSelectedProfileId(value);
    try {
      await setConversationProfile(conversationId, profileId);
      if (profileId) {
        setSource("explicit");
      } else {
        // После сброса — проверяем, есть ли дефолтный
        const convProfile = await getConversationProfile(conversationId);
        setSource(convProfile.source);
        setSelectedProfileId(convProfile.profile?.id || "");
      }
      onProfileChange?.();
    } catch {
      // Ошибка
    }
  };

  const getOptionLabel = (p: UserProfile) => {
    if (source === "default" && p.id === selectedProfileId) {
      return `${p.name} (по умолч.)`;
    }
    return p.name;
  };

  return (
    <select
      className="chat-profile-select"
      value={selectedProfileId}
      onChange={(e) => handleChange(e.target.value)}
      title="Профиль (system prompt)"
    >
      <option value="">Без профиля</option>
      {profiles.map((p) => (
        <option key={p.id} value={p.id}>
          {getOptionLabel(p)}
        </option>
      ))}
    </select>
  );
}

export default ProfileSelector;
