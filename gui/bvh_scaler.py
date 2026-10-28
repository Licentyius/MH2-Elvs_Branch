#############################################################################
##
## BVH Scale Tool Integrated v1.0 (First Run)
## Part of the MakeHuman 2 Project contributed by Elvaerwyn_MH2 2026 by Suggestions from Punkduck and use of external template
##
#############################################################################

import os

def scale_blender_bvh_file(source_filename, directory):
    """
    EXACT STANDALONE LOGIC WITH INITIAL LOCATION NORMALIZATION
    Scales translations while subtracting the very first frame's horizontal 
    positions 
    """
    base_name = os.path.basename(source_filename)
    dest_filename = os.path.join(directory, "scaled_" + base_name)

    # State tracking variables to normalize horizontal offsets dynamically
    start_x = None
    start_z = None

    try:
        with open(source_filename, "r") as source, open(dest_filename, "w") as dest:
            for line in source:
                words = line.split()
                if len(words) == 0:
                    dest.write(line)
                    continue

                # 1. PROCESS BONE OFFSETS (HIERARCHY)
                if len(words) > 1 and words[1].upper() == "OFFSET":
                    val_x = float(words[2]) * 10.0
                    val_y = float(words[3]) * 10.0
                    val_z = float(words[4]) * 10.0
                    dest.write(f"  OFFSET {val_x:.4f} {val_y:.4f} {val_z:.4f}\n")
                    continue

                # 2. PROCESS TIMELINE ANIMATION DATA ROWS (MOTION)
                is_frame = False
                try:
                    float(words[0])
                    is_frame = True
                except (ValueError, IndexError):
                    pass

                if is_frame:
                    # Capture the initial starting offsets on the very first frame line
                    if start_x is None:
                        start_x = float(words[0])
                        start_z = float(words[2])

                    scaled_words = []
                    for i, word in enumerate(words):
                        val = float(word)
                        
                        # Apply the 10x meter-to-decimeter conversion to translations
                        if i == 0:
                            # Normalize X coordinate (Left/Right) back to center 0
                            val = (val - start_x) * 10.0
                        elif i == 1:
                            # Vertical height column (Preserve Leg/Hip stance heights completely!)
                            val *= -10.0
                        elif i == 2:
                            # Normalize Z coordinate (Forward/Backward Stride) back to center 0
                            val = (val - start_z) * 10.0
                        
                        scaled_words.append(f"{val:.4f}")
                    
                    dest.write(" ".join(scaled_words) + "\n")
                    continue

                dest.write(line)

        return True, f"scaled_{base_name}"
    except Exception as e:
        return False, str(e)

