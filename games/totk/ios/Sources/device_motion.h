/* The phone gyro's hand-over and sensitivity APIs, kept by the iPhone / iPad motion aiming (phone_motion.m).
   Main thread unless noted. The Settings switch and the app wiring stay phone_motion's own (TOTK_PHONE_GYRO). */
#import <Foundation/Foundation.h>

void totk_device_motion_note_touch(void);      /* the touch layer saw a finger: the phone's gyro takes the aiming over */
double totk_device_motion_sensitivity(void);   /* the player's gain, 0.1-2 (Documents/save/motion.json), 1 by default */
void totk_device_motion_set_sensitivity(double percent);  /* 10-200: saves it and applies it to the running sensor */
