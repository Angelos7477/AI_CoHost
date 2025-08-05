📦 1. Add the Prompt File
Go to your prompts/ folder (or wherever you're storing prompt text files).

Add a new .txt file named after your desired personality, e.g.:
conspiracist.txt
This file should contain the system prompt used by the AI for that personality.
Example:
You are a paranoid conspiracy theorist. Everything has a deeper meaning. Speak intensely, ramble if needed, and turn ordinary gameplay moments into wild conspiracies.


🎨 2. Add the Personality Icon
Go to the public/icons/ folder (or wherever the overlay HTML expects icons).
Add a PNG file for your new personality.
Dimensions: 64x64 pixels
Format: PNG
Transparent background recommended
File name must match the personality name:
icons/conspiracist.png
🧠 3. Update the Personality Map (Optional)
If you're using a dictionary (like iconMap) in your overlay HTML or Python script, make sure to add the new personality:
const iconMap = {
  ...
  "conspiracist": "icons/conspiracist.png",
};

3. Change valid modes in zorobot. Also change random prompts on prompts/user_prompts, also change voice name in zorobot.
