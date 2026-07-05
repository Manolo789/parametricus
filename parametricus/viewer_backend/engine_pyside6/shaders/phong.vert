#version 330 core

layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

out vec3 FragPos;
out vec3 Normal;

void main()
{
    vec4 world = model * vec4(position,1.0);

    FragPos = world.xyz;

    Normal = mat3(transpose(inverse(model))) * normal;

    gl_Position =
        projection *
        view *
        world;
}
