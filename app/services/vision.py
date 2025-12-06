from services.openrouter import openrouter
import base64

class VisionService:
    async def extract_vin_from_image(self, image_data: str) -> dict:
        """
        Extract VIN from a base64 encoded image using Gemini Flash via OpenRouter.
        """
        # Ensure image_data has the prefix
        if "," in image_data:
            header, base64_str = image_data.split(",", 1)
        else:
            base64_str = image_data
            header = "data:image/jpeg;base64"

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the 17-character Vehicle Identification Number (VIN) from this image. Return ONLY the VIN as a string. If no VIN is visible or it is illegible, return 'NOT_FOUND'. Do not include any other text."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"{header},{base64_str}"
                        }
                    }
                ]
            }
        ]

        try:
            # Use 'structured' model (Gemini Flash) which is multimodal
            content, _ = await openrouter.chat_completion(
                model_key="structured",
                messages=messages,
                temperature=0.1,
                max_tokens=50
            )
            
            vin = content.strip().upper().replace(" ", "").replace("-", "")
            
            if "NOT_FOUND" in vin or len(vin) < 10: # Basic sanity check
                return {"success": False, "error": "VIN not found in image"}
                
            return {"success": True, "vin": vin}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

vision_service = VisionService()
