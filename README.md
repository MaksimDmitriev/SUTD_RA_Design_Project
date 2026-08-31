# SortiBot

SortiBot is a vision-guided object-sorting robot developed by an SUTD Master's student. Built on the MasterPi platform, it uses a camera and a custom YOLO model to detect objects on the floor, estimate their position, approach them, pick them up, and place them in a class-specific location.

The current prototype demonstrates two categories: red useful objects and purple trash. Its perception model can be retrained to recognize additional object classes.

## How it works

1. The camera observes the floor in front of the robot.
2. The object detector identifies and classifies a target.
3. The robot estimates the target's position and approaches it in measured steps.
4. The arm aligns with and picks up the object.
5. The detected class determines where the object is released.

## Video demonstration

[Watch SortiBot in action on YouTube](https://www.youtube.com/watch?v=B0TwQD-e6d0)

## Project article

[Read about building SortiBot on Medium](https://medium.com/@maksim.a.dmitriev/building-sortibot-teaching-a-small-robot-to-find-pick-up-and-sort-objects-4f28a3799347)

## Project webasite

[View the SortiBot project website on GitHub](https://github.com/MaksimDmitriev/SUTD_RA_Design_Project)

## Project software

The [`Web-dashboard`](Web-dashboard/) directory contains the React interface, FastAPI backend, computer-vision pipeline, and robot-control code. For installation, deployment, and operating instructions, see the [dashboard README](Web-dashboard/README.md).
